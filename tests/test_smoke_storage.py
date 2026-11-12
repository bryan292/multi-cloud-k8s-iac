"""Exercise storage lifecycle and cleanup without allocating cloud resources."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class StorageSmokeTests(unittest.TestCase):
    def test_provider_selection_persistence_and_failure_cleanup(self):
        for provider in ('aws', 'azure'):
            for proof, encrypted in (('persistence-ok', True), ('corrupt-data', True), ('persistence-ok', False)):
                with self.subTest(provider=provider, proof=proof, encrypted=encrypted), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / 'scripts').mkdir()
                    (root / 'schemas').mkdir()
                    (root / 'bin').mkdir()
                    for filename in ('config.py', 'smoke-storage.sh'):
                        shutil.copyfile(Path('scripts') / filename, root / 'scripts' / filename)
                    shutil.copyfile('schemas/config-v1.json', root / 'schemas/config-v1.json')
                    shutil.copyfile(f'config.{provider}.yaml_example', root / 'selected.yaml')
                    (root / 'config.yaml').write_text('invalid default config')
                    fake = root / 'bin/fake'
                    fake.write_text('#!' + sys.executable + '\n' + '''
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['SMOKE_COMMAND_LOG'], 'a') as log:
    log.write(json.dumps([name, *args]) + '\\n')
if name == 'kubectl':
    if args[:2] == ['get', 'pvc']: print('test-pv')
    elif args[:2] == ['get', 'pv']: print('vol-isolated-test')
    elif args[0] == 'exec' and 'cat' in args: print(os.environ['SMOKE_PROOF'])
    elif args[0] == 'apply': sys.stdin.read()
elif name == 'aws' and args[:2] == ['ec2', 'describe-volumes']: print(os.environ['SMOKE_ENCRYPTED'])
elif name == 'az' and args[:2] == ['disk', 'show']: print('EncryptionAtRestWithPlatformKey' if os.environ['SMOKE_ENCRYPTED'] == 'True' else 'None')
''')
                    fake.chmod(0o755)
                    for executable in ('kubectl', 'aws', 'az'):
                        (root / 'bin' / executable).symlink_to(fake)
                    log = root / 'commands.jsonl'
                    env = dict(os.environ, PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'],
                               IAC_CONFIG=str(root / 'selected.yaml'), KUBECONFIG=str(root / 'selected-kubeconfig.yaml'),
                               SMOKE_COMMAND_LOG=str(log), SMOKE_PROOF=proof, SMOKE_ENCRYPTED=str(encrypted), TEST_BACKUP='0')
                    result = subprocess.run(['bash', str(root / 'scripts/smoke-storage.sh')],
                                            env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode == 0, proof == 'persistence-ok' and encrypted, result.stdout + result.stderr)
                    commands = [json.loads(line) for line in log.read_text().splitlines()]
                    self.assertTrue(any(command[:3] == ['kubectl', 'delete', 'namespace'] for command in commands))
                    self.assertEqual(any(command[:3] == ['aws', 'ec2', 'delete-volume'] for command in commands), provider == 'aws')
                    self.assertFalse(any(command[0] == ('aws' if provider == 'azure' else 'az') for command in commands))
