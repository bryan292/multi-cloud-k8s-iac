"""CI-008: TLS preservation and process-owned tunnel cleanup without cloud calls."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'ci' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class TunnelTests(unittest.TestCase):
    def test_tls_name_ca_and_credentials_are_preserved(self):
        kube = module('kubeconfig')
        original = {'current-context': 'test', 'contexts': [{'name': 'test', 'context': {'cluster': 'test', 'user': 'user'}}],
                    'clusters': [{'name': 'test', 'cluster': {'server': 'https://api.example.test', 'certificate-authority-data': 'encoded-ca'}}],
                    'users': [{'name': 'user', 'user': {'exec': {'command': 'cloud-login'}}}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kubeconfig'
            path.write_text(yaml.safe_dump(original))
            kube.use_tunnel(path)
            result = yaml.safe_load(path.read_text())
            cluster = result['clusters'][0]['cluster']
            self.assertEqual(cluster['server'], 'https://127.0.0.1:8443')
            self.assertEqual(cluster['tls-server-name'], 'api.example.test')
            self.assertEqual(cluster['certificate-authority-data'], 'encoded-ca')
            self.assertEqual(result['users'], original['users'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for bad in ({'server': 'http://api.example.test'}, {'server': 'https://api.example.test:444'},
                        {'insecure-skip-tls-verify': True}, {'certificate-authority-data': ''},
                        {'proxy-url': 'http://unexpected'}, {'server': 'https://user:password@api.example.test'}):
                data = json.loads(json.dumps(original));data['clusters'][0]['cluster'].update(bad)
                path.write_text(yaml.safe_dump(data))
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    kube.use_tunnel(path)

    def test_tunnel_lifecycle_and_idempotent_cleanup(self):
        tunnel = module('tunnel')
        with tempfile.TemporaryDirectory(dir='/tmp', prefix='ci-tunnel-') as directory:
            root = Path(directory)
            executable = root / 'aws'
            executable.write_text('#!' + sys.executable + '\n' + '''
import json,os,socket,sys
from pathlib import Path
if 'terminate-session' in sys.argv:
 Path(os.environ['TUNNEL_TEST_ARGS']+'.terminated').write_text('ok');sys.exit(0)
Path(os.environ['TUNNEL_TEST_ARGS']).write_text(json.dumps(sys.argv[1:]))
print('Starting session with SessionId: test-session',flush=True)
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',8443));s.listen()
while True:
 c,_=s.accept();c.close()
''')
            executable.chmod(0o700)
            job = root / 'job'
            with patch.dict(os.environ, {'PATH': str(root) + os.pathsep + os.environ['PATH'], 'TUNNEL_TEST_ARGS': str(root / 'args.json')}):
                try:
                    tunnel.start(job, 'i-test', 'fixed-document', 'us-east-1')
                    self.assertTrue((job / 'ready').exists())
                    with self.assertRaises(ValueError):
                        tunnel.start(job, 'i-test', 'fixed-document', 'us-east-1')
                    args = json.loads((root / 'args.json').read_text())
                    self.assertNotIn('--parameters', args)
                    self.assertEqual(args[-1], 'fixed-document')
                finally:
                    tunnel.stop(job)
                tunnel.stop(job)
                self.assertFalse((job / 'control.sock').exists())
                self.assertFalse((job / 'ready').exists())
                self.assertTrue((root / 'args.json.terminated').exists())

    def test_dead_session_fails_before_ready(self):
        tunnel = module('tunnel')
        from unittest.mock import Mock
        with self.assertRaises(ValueError):
            tunnel.wait_ready(Mock(poll=lambda: 1))

    def test_remote_cleanup_failure_is_not_silent(self):
        tunnel = module('tunnel')
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'session.log'
            log.write_text('Starting session with SessionId: test-session')
            with patch.object(tunnel.subprocess, 'run', return_value=Mock(returncode=1)), self.assertRaises(ValueError):
                tunnel.terminate_remote(log, 'us-east-1', required=True)
            log.write_text('unexpected CLI output')
            with self.assertRaises(ValueError):
                tunnel.terminate_remote(log, 'us-east-1', required=True)
            (root / 'cleanup_failed').touch()
            with self.assertRaises(ValueError):
                tunnel.stop(root)
