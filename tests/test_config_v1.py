"""SPEC-001 offline acceptance tests (CFG-001 through CFG-006, CFG-009/010)."""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from scripts.config import SCHEMA, load_config, validate


class VersionedConfigurationTests(unittest.TestCase):
    def test_schema_and_provider_examples(self):
        Draft202012Validator.check_schema(SCHEMA)
        for provider in ('aws', 'azure'):
            with self.subTest(provider=provider):
                load_config(f'config.{provider}.yaml_example')

    def test_reject_invalid_contracts(self):
        base = load_config('config.aws.yaml_example')
        changes = [
            (('schema_version',), 2), (('schema_version',), True),
            (('global', 'provider'), 'gcp'),
            (('global', 'cluster_name'), '../invalid'),
            (('aws', 'account_id'), 123456789012),
            (('eks', 'node_scaling', 'min'), True),
            (('platform', 'commit'), 'main'),
            (('application', 'enabled'), True),
            (('platform', 'token'), 'SECRET_SENTINEL'),
            (('eks', 'admin_cidrs'), ['0.0.0.0/0']),
            (('eks', 'node_scaling', 'desired'), 100),
        ]
        for path, value in changes:
            c = copy.deepcopy(base)
            parent = c
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError) as error:
                validate(c)
            self.assertNotIn('SECRET_SENTINEL', str(error.exception))
        del base['schema_version']
        with self.assertRaises(ValueError):
            validate(base)

    def test_unknown_fields_at_every_object(self):
        base = load_config('config.yaml_example')
        def paths(value, path=()):
            if isinstance(value, dict):
                if path != ('global', 'common_tags'):
                    yield path
                for key, item in value.items():
                    yield from paths(item, (*path, key))
        for path in paths(base):
            c = copy.deepcopy(base)
            parent = c
            for key in path:
                parent = parent[key]
            parent['secret'] = 'SECRET_SENTINEL'
            with self.subTest(path=path), self.assertRaises(ValueError) as error:
                validate(c)
            self.assertNotIn('SECRET_SENTINEL', str(error.exception))

    def test_migration_is_repeatable_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'config.yaml'
            original = Path('tests/fixtures/config-legacy.yaml').read_bytes()
            source.write_bytes(original)
            cmd = [sys.executable, 'scripts/migrate-config.py', str(source)]
            result = subprocess.run(cmd, capture_output=True, check=True).stdout
            self.assertEqual(source.read_bytes(), original)
            migrated = yaml.safe_load(result)
            validate(migrated)
            expected = yaml.safe_load(original)
            expected['schema_version'] = 1
            self.assertEqual(migrated, expected)
            subprocess.run([*cmd, '--in-place'], check=True)
            self.assertEqual(source.read_bytes(), result)
            self.assertEqual(source.with_suffix('.yaml.bak').read_bytes(), original)
            self.assertEqual(subprocess.run(cmd, capture_output=True, check=True).stdout, result)
            subprocess.run([*cmd, '--in-place'], check=True)
            # An existing backup must never be overwritten.
            source.write_bytes(original)
            failed = subprocess.run([*cmd, '--in-place'], capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(source.with_suffix('.yaml.bak').read_bytes(), original)

    def test_names_networks_and_credential_urls(self):
        cases = [
            ('aws', ('aws', 'bucket_name'), value)
            for value in ('192.168.1.1', 'bad..bucket', 'xn--reserved', 'reserved--x-s3', 'reserved-s3alias', 'Uppercase')
        ] + [
            ('azure', ('azure', 'state', 'resource_group_name'), 'bad.'),
            ('azure', ('azure', 'state', 'storage_account_name'), 'Bad-Name'),
            ('azure', ('azure', 'state', 'container_name'), 'bad--container'),
            ('azure', ('azure', 'network', 'vnet_cidr'), '10.71.0.0/16'),
            ('azure', ('azure', 'network', 'api_server_authorized_ip_ranges'), ['::/0']),
            ('azure', ('azure', 'network', 'api_server_authorized_ip_ranges'), ['2001:db8::/32']),
            ('azure', ('azure', 'node_pool', 'desired'), 99),
            ('aws', ('platform', 'repository'), 'https://user:SECRET_SENTINEL@example.com/repo'),
            ('aws', ('platform', 'repository'), 'https://example.com/repo?token=SECRET_SENTINEL'),
        ]
        for provider, path, value in cases:
            c = load_config(f'config.{provider}.yaml_example')
            parent = c
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = value
            with self.subTest(path=path, provider=provider), self.assertRaises(ValueError) as error:
                validate(c)
            self.assertNotIn('SECRET_SENTINEL', str(error.exception))
        c = load_config('config.azure.yaml_example')
        c['global']['environment'] = 'a' * 20
        c['global']['cluster_name'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, '63'):
            validate(c)

    def test_cli_errors_omit_secrets_and_cloud_is_not_needed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'config.yaml'
            for text in ('global: [SECRET_SENTINEL', 'global: {}\nglobal: SECRET_SENTINEL',
                         'schema_version: 99\ntoken: SECRET_SENTINEL'):
                source.write_text(text)
                for script, args in [('scripts/preflight.py', ['--offline', '--config']),
                                     ('scripts/migrate-config.py', [])]:
                    result = subprocess.run([sys.executable, script, *args, str(source)], capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('SECRET_SENTINEL', result.stdout + result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_historical_optional_attributes_keep_terraform_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'config.yaml'
            legacy = yaml.safe_load(Path('tests/fixtures/config-legacy.yaml').read_text())
            legacy['application'] = {'enabled': False}
            legacy['platform'].pop('secret_name')
            source.write_text(yaml.safe_dump(legacy))
            result = subprocess.run([sys.executable, 'scripts/migrate-config.py', str(source)], check=True, capture_output=True, text=True)
            migrated = validate(yaml.safe_load(result.stdout))
            self.assertEqual(migrated['application'], {'enabled': False, 'repository': '', 'commit': '', 'path': './', 'secret_name': ''})
            self.assertEqual(migrated['platform']['secret_name'], '')
