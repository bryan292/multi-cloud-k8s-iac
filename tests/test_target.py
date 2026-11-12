"""CFG-007: no Terraform subprocess may run before identity/backend checks pass."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import bootstrap, deploy, target
from scripts.config import load_config


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.aws = load_config('config.aws.yaml_example')
        self.azure = load_config('config.azure.yaml_example')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_aws_identity_mismatch_and_root(self):
        for identity in ({'Account': '999999999999', 'Arn': 'hidden'},
                         {'Account': self.aws['aws']['account_id'], 'Arn': 'arn:aws:iam::123456789012:root'}):
            with patch.object(target, 'command_json', return_value=identity), self.assertRaises(ValueError):
                target.check_identity(self.aws, {})

    def test_azure_identity_mismatch(self):
        a = self.azure['azure']
        for identity in ({'id': 'wrong', 'tenantId': a['tenant_id']},
                         {'id': a['subscription_id'], 'tenantId': 'wrong'}):
            with patch.object(target, 'command_json', return_value=identity), self.assertRaises(ValueError):
                target.check_identity(self.azure, {})

    def test_matching_identities(self):
        for config, identity in [(self.aws, {'Account': self.aws['aws']['account_id'], 'Arn': 'arn:aws:iam::123456789012:role/Test'}),
                                 (self.azure, {'id': self.azure['azure']['subscription_id'], 'tenantId': self.azure['azure']['tenant_id']})]:
            with patch.object(target, 'command_json', return_value=identity):
                self.assertEqual(target.check_identity(config, {}), identity)

    def test_aws_backend_checks_owner_and_region(self):
        with patch.object(target, 'command_json', side_effect=[{}, {'LocationConstraint': None}]) as query:
            target.check_backend(self.aws, {})
            for call in query.call_args_list:
                self.assertIn('--expected-bucket-owner', call.args)
                self.assertIn(self.aws['aws']['account_id'], call.args)
        with patch.object(target, 'command_json', side_effect=[{}, {'LocationConstraint': 'eu-west-1'}]), self.assertRaisesRegex(ValueError, 'state_region'):
            target.check_backend(self.aws, {})

    def test_backend_cloud_failure_is_fatal(self):
        for config in (self.aws, self.azure):
            with patch.object(target, 'command_json', side_effect=ValueError('denied')), self.assertRaises(ValueError):
                target.check_backend(config, {})

    def azure_account(self):
        a = self.azure['azure']
        s = a['state']
        return {'id': f"/subscriptions/{a['subscription_id']}/resourceGroups/{s['resource_group_name']}/providers/Microsoft.Storage/storageAccounts/{s['storage_account_name']}"}

    def test_azure_backend_checks_subscription_and_container(self):
        with patch.object(target, 'command_json', side_effect=[self.azure_account(), {'exists': True}]) as query:
            target.check_backend(self.azure, {})
            self.assertIn('--subscription', query.call_args_list[0].args)
            self.assertIn('login', query.call_args_list[1].args)
        for responses in ([{'id': 'wrong'}], [self.azure_account(), {'exists': False}]):
            with patch.object(target, 'command_json', side_effect=responses), self.assertRaises(ValueError):
                target.check_backend(self.azure, {})

    def test_credential_environment_matches_selected_cloud(self):
        original = {'AWS_ACCESS_KEY_ID': 'SECRET', 'AWS_SECRET_ACCESS_KEY': 'SECRET', 'AWS_PROFILE': 'wrong',
                    'ARM_CLIENT_SECRET': 'SECRET', 'ARM_USE_OIDC': 'true', 'AZURE_STORAGE_KEY': 'SECRET'}
        with patch.dict(os.environ, original, clear=True):
            aws = target.cloud_environment(self.aws)
            azure = target.cloud_environment(self.azure)
        self.assertEqual(aws['AWS_PROFILE'], self.aws['aws']['profile'])
        self.assertNotIn('AWS_ACCESS_KEY_ID', aws)
        self.assertNotIn('ARM_CLIENT_SECRET', azure)
        self.assertNotIn('AZURE_STORAGE_KEY', azure)
        self.assertEqual(azure['ARM_USE_CLI'], 'true')
        self.assertEqual(azure['ARM_USE_OIDC'], 'false')

    def test_override_environment_is_rejected(self):
        for key in ('TF_VAR_account_id', 'TF_CLI_ARGS', 'TF_CLI_ARGS_plan', 'TF_DATA_DIR', 'TG_CONFIG'):
            with patch.dict(os.environ, {key: 'SECRET'}, clear=True), self.assertRaises(ValueError) as error:
                target.cloud_environment(self.aws)
            self.assertNotIn('SECRET', str(error.exception))

    def test_cloud_errors_do_not_expose_output_or_arguments(self):
        errors = [subprocess.CalledProcessError(1, ['SECRET'], output='SECRET', stderr='SECRET'),
                  subprocess.TimeoutExpired(['SECRET'], 1), FileNotFoundError('SECRET')]
        for error in errors:
            with patch.object(subprocess, 'run', side_effect=error), self.assertRaises(ValueError) as caught:
                target.command_json('aws', 'SECRET')
            self.assertNotIn('SECRET', str(caught.exception))

    def test_pin_rejects_destination_change_and_allows_both_providers(self):
        stages = deploy.stages('aws')
        target.pin_target(self.aws, self.root, stages)
        target.pin_target(self.aws, self.root, stages)
        target.pin_target(self.aws, self.root, ['bootstrap'])
        target.pin_target(self.azure, self.root, deploy.stages('azure'))
        changed = copy.deepcopy(self.aws)
        changed['aws']['bucket_name'] = 'another-state-bucket'
        with self.assertRaisesRegex(ValueError, 'previously verified'):
            target.pin_target(changed, self.root, stages)

    def test_cached_backend_rejects_changed_coordinates(self):
        stage = 'azure/aks'
        backend_type, config = target.backend_config(self.azure, stage)
        path = self.root / 'deployment-config' / stage / '.terragrunt-cache/cache/module/.terraform/terraform.tfstate'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'backend': {'type': backend_type, 'config': config}}))
        target.check_cached_backends(self.azure, self.root, [stage])
        config['key'] = 'wrong-state'
        path.write_text(json.dumps({'backend': {'type': backend_type, 'config': config}}))
        with self.assertRaisesRegex(ValueError, 'initialized destination'):
            target.check_cached_backends(self.azure, self.root, [stage])

    def test_pre_plan_stops_before_backend_on_identity_failure(self):
        with patch.object(target, 'check_identity', side_effect=ValueError('identity')), patch.object(target, 'check_backend') as backend:
            with self.assertRaises(ValueError):
                target.pre_plan(self.aws, self.root, deploy.stages('aws'))
            backend.assert_not_called()
            self.assertFalse((self.root / '.deployment-targets').exists())

    def test_deploy_never_runs_terraform_after_failed_preflight(self):
        from scripts import operations
        from unittest.mock import Mock
        for provider in ('aws', 'azure'):
            for action in ('deploy', 'destroy'):
                with self.subTest(provider=provider, action=action):
                    path = self.root / 'config.json'
                    operations.atomic_json(path, getattr(self, provider))
                    runner = Mock()
                    engine = operations.Operations(self.root, path, runner=runner)
                    with patch.object(operations, 'pre_plan', side_effect=ValueError('mismatch')):
                        with self.assertRaises(ValueError):
                            engine.execute(action, confirm=f'{provider}/dev/demo')
                    runner.run.assert_not_called()

    def test_deploy_compatibility_wrapper_delegates_to_canonical_cli(self):
        from scripts import iac
        with patch.object(iac, 'main', return_value=0) as run:
            self.assertEqual(deploy.main(['--json', 'plan']), 0)
        run.assert_called_once_with(['--json', 'plan'])

    def test_bootstrap_checks_identity_before_terraform(self):
        with patch.object(bootstrap, 'ROOT', self.root), patch.object(bootstrap, 'load_config', return_value=self.azure), patch.object(bootstrap, 'check_identity', side_effect=ValueError('mismatch')), patch.object(bootstrap.subprocess, 'call') as run:
            with self.assertRaises(ValueError):
                bootstrap.main(['plan'])
            run.assert_not_called()

    def test_bootstrap_local_state_mismatch(self):
        state = {'resources': [{'type': 'azurerm_storage_account', 'instances': [{'attributes': {'name': 'wrong', 'id': '/subscriptions/wrong/resourceGroups/wrong'}}]}]}
        (self.root / 'terraform.tfstate').write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, 'bootstrap.state'):
            target.check_bootstrap_state(self.azure, self.root)

    def test_bootstrap_rejects_destination_overrides(self):
        for arguments in (['plan', '-var=account_id=SECRET'], ['init', '-backend-config=SECRET'],
                          ['plan', '-state=SECRET'], ['init', '-migrate-state'], ['apply', 'foreign.tfplan']):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError) as error:
                target.check_bootstrap_arguments(arguments)
            self.assertNotIn('SECRET', str(error.exception))
        target.check_bootstrap_arguments(['plan', '-input=false', '-out=review.tfplan'])

    def test_bootstrap_and_deployment_have_separate_pins(self):
        target.pin_target(self.azure, self.root, ['bootstrap'])
        target.pin_target(self.azure, self.root, deploy.stages('azure'))
        self.assertEqual(len(list((self.root / '.deployment-targets').glob('*.json'))), 2)

    def test_existing_bootstrap_backend_is_checked_before_terraform(self):
        with patch.object(bootstrap, 'ROOT', self.root), patch.object(bootstrap, 'load_config', return_value=self.azure), patch.object(bootstrap, 'check_bootstrap_state', return_value=True), patch.object(bootstrap, 'check_identity'), patch.object(bootstrap, 'check_backend', side_effect=ValueError('backend mismatch')), patch.object(bootstrap.subprocess, 'call') as run:
            with self.assertRaisesRegex(ValueError, 'backend mismatch'):
                bootstrap.main(['plan'])
            run.assert_not_called()
