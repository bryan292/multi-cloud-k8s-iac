"""OPS-001..010: exercise plans, approval, ordering, interruption and isolation."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import operations as ops
from scripts.config import load_config


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.outputs = {'cluster_name': {'value': 'test-cluster'}}
        self.fail_apply = None
        self.drift = False

    def run(self, args, cwd, env, log, capture=False, accepted=(0,)):
        stage = str(cwd).split('deployment-config/')[-1]
        self.calls.append((stage, list(args), dict(env)))
        command = args[1]
        if command == 'apply' and stage == self.fail_apply:
            raise ops.ToolFailure('simulated apply interruption')
        if command == 'output':
            return 0, copy.deepcopy(self.outputs)
        if command == 'show':
            return 0, {'resource_changes': [{'change': {'actions': ['create']}}]}
        if command == 'plan':
            output = next((arg[5:] for arg in args if arg.startswith('-out=')), None)
            if output:
                Path(output).write_bytes(b'opaque-terraform-plan')
                return 2, None
            return (2 if self.drift else 0), None
        return 0, None


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config('config.azure.yaml_example')
        self.path = self.root / 'config.json'
        ops.atomic_json(self.path, self.config)
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/source.py').write_text('# source\n')
        self.runner = FakeRunner()
        self.events = []
        self.preflight = patch.object(ops, 'pre_plan', return_value={})
        self.preflight.start()
        self.addCleanup(self.preflight.stop)

    def engine(self):
        return ops.Operations(self.root, self.path, lambda **event: self.events.append(event), self.runner)

    def plan(self):
        engine = self.engine()
        directory = engine.execute('deploy', requested=['azure/aks'], plan_only=True)
        return directory, ops.file_digest(directory / 'manifest.json')

    def test_plan_never_applies_and_has_private_artifacts(self):
        directory, _ = self.plan()
        self.assertFalse(any(args[1] == 'apply' for _, args, _ in self.runner.calls))
        self.assertEqual((directory / 'manifest.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((directory / 'azure-aks.tfplan').stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((directory / 'manifest.json').read_text())['stages']['azure/aks']['summary']['create'], 1)

    def test_reviewed_plan_is_applied_without_replanning(self):
        directory, digest = self.plan()
        self.runner.calls.clear()
        self.engine().execute('deploy', plan_dir=directory, plan_digest=digest)
        self.assertEqual([args[1] for _, args, _ in self.runner.calls], ['apply'])

    def test_wrong_digest_or_missing_approval_blocks_apply(self):
        directory, _ = self.plan()
        for supplied in (None, 'incorrect'):
            self.runner.calls.clear()
            with self.assertRaises(ValueError):
                self.engine().execute('deploy', plan_dir=directory, plan_digest=supplied)
            self.assertFalse(self.runner.calls)

    def test_changed_binary_blocks_apply(self):
        directory, digest = self.plan()
        (directory / 'azure-aks.tfplan').write_bytes(b'changed')
        self.runner.calls.clear()
        with self.assertRaisesRegex(ValueError, 'saved plan changed'):
            self.engine().execute('deploy', plan_dir=directory, plan_digest=digest)
        self.assertFalse(self.runner.calls)

    def test_changed_config_source_and_snapshot_are_rejected(self):
        for kind in ('config', 'source', 'snapshot'):
            with self.subTest(kind=kind):
                directory, digest = self.plan()
                changed = dict(self.config, application={**self.config['application'], 'path': './changed'})
                if kind == 'config':
                    ops.atomic_json(self.path, changed)
                elif kind == 'snapshot':
                    ops.atomic_json(directory / 'config.json', changed)
                else:
                    (self.root / 'scripts/source.py').write_text('# changed\n')
                self.runner.calls.clear()
                with self.assertRaises(ValueError):
                    self.engine().execute('deploy', plan_dir=directory, plan_digest=digest)
                self.assertFalse(self.runner.calls)
                ops.atomic_json(self.path, self.config)
                (self.root / 'scripts/source.py').write_text('# source\n')

    def test_dependency_changes_block_saved_plan(self):
        engine = self.engine()
        directory = engine.execute('deploy', requested=['kubernetes'], plan_only=True)
        digest = ops.file_digest(directory / 'manifest.json')
        self.runner.outputs['cluster_name']['value'] = 'another-cluster'
        self.runner.calls.clear()
        with self.assertRaisesRegex(ValueError, 'upstream outputs'):
            self.engine().execute('deploy', plan_dir=directory, plan_digest=digest)
        self.assertFalse(any(args[1] == 'apply' for _, args, _ in self.runner.calls))

    def test_deploy_orders_plan_apply_per_stage(self):
        self.engine().execute('deploy')
        lifecycle = [(stage, args[1]) for stage, args, _ in self.runner.calls if args[1] in ('plan', 'apply')]
        self.assertEqual(lifecycle, [(stage, action) for stage in ops.stages('azure') for action in ('plan', 'apply')])

    def test_resume_verifies_completed_stage_and_replans_failed_apply(self):
        self.runner.fail_apply = 'kubernetes'
        engine = self.engine()
        with self.assertRaises(ops.ToolFailure):
            engine.execute('deploy')
        self.runner.fail_apply = None
        self.runner.calls.clear()
        self.engine().execute('deploy', resume=engine.run_dir)
        applied = [stage for stage, args, _ in self.runner.calls if args[1] == 'apply']
        self.assertEqual(applied, ['kubernetes', 'kube_resources'])
        self.assertTrue(any(event['event'] == 'resume_verified' for event in self.events))

    def test_resume_rejects_drift_in_completed_stage(self):
        engine = self.engine()
        directory = engine.execute('deploy')
        self.runner.drift = True
        self.runner.calls.clear()
        with self.assertRaisesRegex(ValueError, 'drift'):
            self.engine().execute('deploy', resume=directory)
        self.assertFalse(any(args[1] == 'apply' for _, args, _ in self.runner.calls))

    def test_destroy_requires_exact_confirmation_and_reverses_stages(self):
        for confirm in (None, 'yes', 'aws/dev/demo'):
            with self.assertRaisesRegex(ValueError, 'confirm-destroy'):
                self.engine().execute('destroy', confirm=confirm)
        self.assertFalse(self.runner.calls)
        self.engine().execute('destroy', confirm='azure/dev/demo')
        self.assertEqual([stage for stage, args, _ in self.runner.calls if args[1] == 'apply'], list(reversed(ops.stages('azure'))))

    def test_selected_stages_cannot_escape_provider_or_duplicate(self):
        for requested in (['../bootstrap'], ['aws/eks'], ['azure/aks', 'azure/aks']):
            with self.assertRaises(ValueError):
                self.engine().execute('deploy', requested=requested)
        self.assertFalse(self.runner.calls)

    def test_lock_blocks_second_operation_for_same_destination(self):
        with self.engine().lock():
            with self.assertRaisesRegex(ValueError, 'another operation'):
                with self.engine().lock():
                    self.fail('second lock acquired')

    def test_kubeconfig_and_cache_are_isolated_by_provider(self):
        azure = self.engine()
        azure.execute('deploy', requested=['azure/aks'], plan_only=True)
        aws_config = load_config('config.aws.yaml_example')
        ops.atomic_json(self.path, aws_config)
        aws = self.engine()
        aws.execute('deploy', requested=['aws/network'], plan_only=True)
        self.assertNotEqual(azure.target_dir, aws.target_dir)
        self.assertNotEqual(azure.env['IAC_KUBECONFIG'], aws.env['IAC_KUBECONFIG'])
        self.assertNotEqual(azure.env['TG_DOWNLOAD_DIR'], aws.env['TG_DOWNLOAD_DIR'])

    def test_manifest_paths_and_action_cannot_be_repurposed(self):
        directory, digest = self.plan()
        with self.assertRaisesRegex(ValueError, 'action/stages'):
            self.engine().execute('destroy', plan_dir=directory, plan_digest=digest, confirm='azure/dev/demo')
        manifest = json.loads((directory / 'manifest.json').read_text())
        manifest['stages']['azure/aks']['plan'] = '../another.tfplan'
        ops.atomic_json(directory / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'applicable state'):
            self.engine().execute('deploy', plan_dir=directory, plan_digest=ops.file_digest(directory / 'manifest.json'))

    def test_destroy_resume_reads_empty_state_without_missing_dependencies(self):
        engine = self.engine()
        directory = engine.execute('destroy', confirm='azure/dev/demo')
        self.runner.calls.clear()
        with patch.object(ops, 'read_remote_state', return_value={'resources': [], 'outputs': {}}):
            self.engine().execute('destroy', resume=directory, confirm='azure/dev/demo')
        self.assertFalse(self.runner.calls)
        with patch.object(ops, 'read_remote_state', return_value={'resources': [{}]}), self.assertRaisesRegex(ValueError, 'drift'):
            self.engine().execute('destroy', resume=directory, confirm='azure/dev/demo')

    def test_bootstrap_uses_existing_state_directory_and_guarded_plan(self):
        with patch.object(ops, 'cloud_environment', return_value={}), patch.object(ops, 'check_identity'), patch.object(ops, 'check_bootstrap_state', return_value=False), patch.object(ops, 'pin_target'), patch.object(ops, 'check_backend') as backend:
            engine = self.engine()
            directory = engine.execute('bootstrap', plan_only=True)
            backend.assert_not_called()
            self.assertEqual([args[1] for _, args, _ in self.runner.calls], ['init', 'plan', 'show'])
            self.assertTrue(all(Path(stage) == self.root.resolve() / 'bootstrap/azure' for stage, _, _ in self.runner.calls))
            self.assertEqual(self.runner.calls[1][2]['TF_VAR_storage_account_name'], self.config['azure']['state']['storage_account_name'])
            engine = self.engine()
            engine.execute('bootstrap', plan_dir=directory, plan_digest=ops.file_digest(directory / 'manifest.json'))
            self.assertEqual(self.runner.calls[-1][1][1], 'apply')

    def test_json_cli_errors_are_parseable_and_omit_input(self):
        import contextlib
        import io
        from scripts import iac
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = iac.main(['--json', 'SECRET_SENTINEL'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())['event'], 'error')
        self.assertNotIn('SECRET_SENTINEL', output.getvalue())

    def test_failed_verification_is_recorded_without_cleanup(self):
        import contextlib
        import io
        from scripts import iac
        output = io.StringIO()
        with patch.object(iac, 'ROOT', self.root), patch.object(ops.Runner, 'run', side_effect=ops.ToolFailure('verification failed')), contextlib.redirect_stdout(output):
            code = iac.main(['--config', str(self.path), '--json', 'verify'])
        self.assertEqual(code, 1)
        manifests = list((self.root / '.iac/runs').glob('*/manifest.json'))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(json.loads(manifests[0].read_text())['status'], 'failed')
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['event'], 'error')

    def test_orphaned_approval_digest_never_starts_an_apply(self):
        with self.assertRaises(ValueError):
            self.engine().execute('deploy', plan_digest='reviewed-digest-without-path')
        self.assertFalse(self.runner.calls)

    def test_malformed_manifest_collection_types_are_rejected(self):
        directory, _ = self.plan()
        original = json.loads((directory / 'manifest.json').read_text())
        for changed in ({'stages': []}, {'order': []}, {'order': [None]}, {'stages': {'azure/aks': []}}):
            with self.subTest(changed=changed):
                ops.atomic_json(directory / 'manifest.json', {**original, **changed})
                with self.assertRaises(ValueError):
                    self.engine().load(directory)
