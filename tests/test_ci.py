"""CI-003/004: encrypted plan transfer and rejection paths."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bundle', ROOT / 'ci/bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


@unittest.skipUnless(shutil.which('gpg'), 'GPG required for artifact encryption integration')
class BundleTests(unittest.TestCase):
    def test_encrypted_roundtrip_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / '.iac/runs/example'
            run.mkdir(parents=True)
            (run / 'manifest.json').write_text('{"version": 1}')
            (run / 'config.json').write_text('{"private": "sensitive-value"}')
            events = root / 'events.json'
            events.write_text(json.dumps({'event': 'run_completed', 'status': 'planned',
                                         'run_dir': str(run), 'plan_digest': bundle.sha(run / 'manifest.json')}))
            encrypted = root / 'plan.gpg'
            with patch('pathlib.Path.cwd', return_value=root), patch.dict(os.environ, {'PLAN_ENCRYPTION_KEY': 'test-secret-' * 6, 'GNUPGHOME': str(root)}):
                metadata = bundle.pack(events, encrypted)
                self.assertNotIn(b'sensitive-value', encrypted.read_bytes())
                with self.assertRaises(ValueError):
                    bundle.unpack(encrypted, '../escape', metadata['bundle_digest'], metadata['plan_digest'])
                with self.assertRaises(ValueError):
                    bundle.unpack(encrypted, 'example', metadata['bundle_digest'], metadata['plan_digest'])
                shutil.rmtree(run)
                with self.assertRaises(ValueError):
                    bundle.unpack(encrypted, 'example', 'wrong', metadata['plan_digest'])
                with self.assertRaises(ValueError):
                    bundle.unpack(encrypted, 'example', metadata['bundle_digest'], 'wrong')
                restored = bundle.unpack(encrypted, 'example', metadata['bundle_digest'], metadata['plan_digest'])
                self.assertEqual(json.loads((restored / 'config.json').read_text())['private'], 'sensitive-value')
                self.assertEqual((restored / 'config.json').stat().st_mode & 0o777, 0o600)
                shutil.rmtree(run)
                encrypted.write_bytes(encrypted.read_bytes()[:-10])
                with self.assertRaises(ValueError):
                    bundle.unpack(encrypted, 'example', bundle.sha(encrypted), metadata['plan_digest'])


class WorkflowTests(unittest.TestCase):
    def test_immutable_actions_and_approval_boundary(self):
        import re
        import yaml
        path = ROOT / '.github/workflows/cloud-operation.yml'
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(workflow['jobs']['apply']['needs'], 'plan')
        self.assertTrue(workflow['jobs']['apply']['environment'].endswith('-apply'))
        self.assertEqual(workflow['concurrency']['cancel-in-progress'], 'false')
        self.assertNotIn('destroy', path.read_text())
        for file in (ROOT / '.github/workflows').glob('*.yml'):
            for use in re.findall(r'uses:\s*([^\s]+)', file.read_text()):
                if not use.startswith('./'):
                    self.assertRegex(use, r'^[^@]+@[0-9a-f]{40}$')
        self.assertIn('artifact-ids: ${{ needs.plan.outputs.artifact_id }}', path.read_text())
        self.assertIn('--plan-digest "$PLAN_DIGEST"', path.read_text())

    def test_oidc_session_provider_environment_and_private_profile(self):
        from scripts.config import load_config
        session_spec = importlib.util.spec_from_file_location('session', ROOT / 'ci/session.py')
        session = importlib.util.module_from_spec(session_spec)
        session_spec.loader.exec_module(session)
        value = load_config(ROOT / 'config.aws.yaml_example')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {'IAC_CONFIG_JSON': json.dumps(value), 'IAC_PROVIDER': 'azure',
                   'IAC_ENVIRONMENT': value['global']['environment'], 'GITHUB_ENV': str(root / 'env'),
                   'AWS_ACCESS_KEY_ID': 'temporary-id', 'AWS_SECRET_ACCESS_KEY': 'temporary-secret',
                   'AWS_SESSION_TOKEN': 'temporary-token'}
            with patch.dict(os.environ, env):
                with self.assertRaises(ValueError):
                    session.prepare(root / 'session')
                os.environ['IAC_PROVIDER'] = 'aws'
                session.prepare(root / 'session')
                credentials = root / 'session/aws-credentials'
                self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
                self.assertIn('aws_session_token = temporary-token', credentials.read_text())
                self.assertNotIn('temporary-token', (root / 'env').read_text())
                os.environ['IAC_ENVIRONMENT'] = 'mismatched'
                with self.assertRaises(ValueError):
                    session.prepare(root / 'session')

    def test_only_owner_may_approve_including_own_dispatch(self):
        import copy
        gate_spec = importlib.util.spec_from_file_location('gate', ROOT / 'ci/check_environment.py')
        gate = importlib.util.module_from_spec(gate_spec)
        gate_spec.loader.exec_module(gate)
        owner = {'type': 'User', 'id': 1}
        reviewer = {'type': 'User', 'reviewer': {'id': 1}}
        valid = {'protection_rules': [{'type': 'required_reviewers', 'reviewers': [reviewer],
                                     'prevent_self_review': False}],
                 'deployment_branch_policy': {'protected_branches': True}}
        gate.enforce(valid, {'protected': True}, owner)
        for allowed in ([], [dict(type='User', reviewer={'id': 2})],
                        [reviewer, dict(type='User', reviewer={'id': 2})],
                        [dict(type='Team', reviewer={'id': 1})]):
            invalid = copy.deepcopy(valid)
            invalid['protection_rules'][0]['reviewers'] = allowed
            with self.subTest(reviewers=allowed), self.assertRaises(ValueError):
                gate.enforce(invalid, {'protected': True}, owner)
        for changed in ({'protection_rules': []}, {'deployment_branch_policy': None},
                        {'protection_rules': [{**valid['protection_rules'][0], 'prevent_self_review': True}]}):
            with self.subTest(change=changed), self.assertRaises(ValueError):
                gate.enforce({**valid, **changed}, {'protected': True}, owner)
        with self.assertRaises(ValueError):
            gate.enforce(valid, {'protected': False}, owner)
        with self.assertRaises(ValueError):
            gate.enforce(valid, {'protected': True}, {'type': 'Organization', 'id': 1})

    def test_ci_kubeconfig_matches_deployed_cluster_names(self):
        from scripts.config import load_config
        from types import SimpleNamespace
        kube_spec = importlib.util.spec_from_file_location('kube', ROOT / 'ci/kubeconfig.py')
        kube = importlib.util.module_from_spec(kube_spec)
        kube_spec.loader.exec_module(kube)
        for provider in ('aws', 'azure'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                (target / 'kubeconfig.yaml').write_text('private configuration')
                value = load_config(ROOT / f'config.{provider}.yaml_example')
                operation = SimpleNamespace(config=value, provider=provider, target_dir=target)
                with patch.object(kube, 'Operations', return_value=operation), patch.object(kube, 'cloud_environment', return_value={}), patch.object(kube, 'check_identity'), patch.object(kube.subprocess, 'run') as run:
                    kube.prepare('unused')
                args = run.call_args_list[0].args[0]
                self.assertEqual(args[args.index('--name') + 1], 'dev-demo-cluster')
                self.assertNotIn('--admin', args)
                self.assertEqual((target / 'kubeconfig.yaml').stat().st_mode & 0o777, 0o600)
