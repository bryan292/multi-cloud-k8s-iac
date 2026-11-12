"""Render every stage without credentials in an isolated repository (CFG-008)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.config import load_config
from scripts.deploy import stages
from scripts.target import backend_config

ROOT = Path(__file__).resolve().parents[1]
MOCKS = {
    'cluster_name': 'render-only-cluster', 'vpc_id': 'vpc-00000000000000000',
    'private_subnets_ids': ['subnet-00000000000000001', 'subnet-00000000000000002'],
    'intra_subnets_ids': ['subnet-00000000000000003', 'subnet-00000000000000004'],
    **{name: 'arn:aws:iam::123456789012:role/RenderOnly' for name in
       ('eks_lb_role_arn', 'eks_cm_role_arn', 'eks_external_dns_role_arn', 'cluster_autoscaler_role_arn')},
}


@unittest.skipUnless(shutil.which('terragrunt') and shutil.which('git'), 'Terragrunt and git required for render integration')
class RenderTests(unittest.TestCase):
    def test_both_clouds_have_unchanged_backend_keys_and_correct_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'deployment-config', root / 'deployment-config',
                            ignore=shutil.ignore_patterns('.terraform', '.terragrunt-cache', '*.tfplan'))
            subprocess.run(['git', 'init', '-q', directory], check=True, capture_output=True)
            # Test-only mocks are injected into the isolated copy, never the real HCL.
            for path in (root / 'deployment-config').rglob('terragrunt.hcl'):
                text = path.read_text()
                text = re.sub(r'(dependency "[^\"]+" \{) ([^\n]+) \}', r'\1\n  \2\n}', text)
                def mocked(match):
                    return (match.group(0) + '\n  skip_outputs = true\n  mock_outputs_allowed_terraform_commands = ["render"]\n'
                            + '  mock_outputs = ' + json.dumps(MOCKS) + '\n')
                text = re.sub(r'dependency "(?:cluster|network)" \{', mocked, text)
                path.write_text(text)
            # Even accidental subprocess cloud auth cannot use the developer's credentials.
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(('AWS_', 'ARM_', 'AZURE_', 'TG_', 'TF_', 'IAC_'))}
            env.update(AWS_EC2_METADATA_DISABLED='true', AWS_SHARED_CREDENTIALS_FILE=str(root / 'no-credentials'),
                       AWS_CONFIG_FILE=str(root / 'no-config'), AZURE_CONFIG_DIR=str(root / 'azure'), TG_TF_PATH='terraform')
            for provider in ('aws', 'azure'):
                config = load_config(ROOT / f'config.{provider}.yaml_example')
                shutil.copyfile(ROOT / f'config.{provider}.yaml_example', root / 'config.yaml')
                # Explicit selection must override even an invalid default configuration.
                selected = root / f'{provider}.json'
                selected.write_text(json.dumps(config))
                (root / 'config.yaml').write_text('invalid default configuration')
                env.update(IAC_CONFIG=str(selected), IAC_KUBECONFIG=str(root / provider / 'kubeconfig.yaml'))
                for stage in stages(provider):
                    with self.subTest(provider=provider, stage=stage):
                        result = subprocess.run(['terragrunt', 'render', '--json', '--no-color'],
                                                cwd=root / 'deployment-config' / stage,
                                                env=env, capture_output=True, text=True, timeout=60)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        rendered = json.loads(result.stdout)
                        backend, expected = backend_config(config, stage)
                        self.assertEqual(rendered['remote_state']['backend'], backend)
                        for key, value in expected.items():
                            self.assertEqual(rendered['remote_state']['config'][key], value)
                        if stage != 'aws/network':
                            self.assertEqual(rendered['inputs']['kubeconfig_path'], env['IAC_KUBECONFIG'])
                        if stage == 'kube_resources':
                            self.assertEqual(rendered['inputs']['provider_name'], provider)
                            self.assertEqual(rendered['inputs']['platform']['path'], f'./clusters/dev/{provider}')
                            self.assertEqual(rendered['inputs']['create_storage_class'], provider == 'aws')
                        if stage == 'azure/aks':
                            self.assertEqual(rendered['inputs']['subscription_id'], config['azure']['subscription_id'])
                        if stage == 'aws/eks':
                            self.assertEqual(rendered['inputs']['account_id'], config['aws']['account_id'])
