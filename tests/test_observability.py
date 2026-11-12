"""OBS-006: a failed exercise must restore the probe and cannot notify outsiders."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
spec = importlib.util.spec_from_file_location('observability_check', Path(__file__).resolve().parents[1] / 'scripts/verify-observability.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ObservabilityProbeTests(unittest.TestCase):
    def observer(self):
        observer = module.Observer.__new__(module.Observer)
        observer.get = Mock(return_value={'config': {'original': 'receivers:\n- name: null-receiver\n  labels: {team: platform}\n'}})
        observer.kube = Mock(return_value={})
        return observer

    def test_failed_probe_is_restored_without_deletion(self):
        observer = self.observer()
        writes = []
        def kube(*args, value=None):
            if value: writes.append(copy.deepcopy(value))
            self.assertNotIn('delete', args)
            return {}
        observer.kube = kube
        observer.until = Mock(side_effect=ValueError('simulated alert timeout'))
        with self.assertRaisesRegex(ValueError, 'timeout'):
            observer.exercise('http://prometheus', 'http://alertmanager')
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0]['spec']['path'], './acceptance-intentionally-missing-path')
        self.assertEqual(writes[1]['spec']['path'], './applications/dev')
        self.assertFalse(writes[1]['spec']['prune'])

    def test_external_notification_receiver_prevents_exercise(self):
        observer = self.observer()
        observer.get.return_value = {'config': {'original': 'receivers:\n- name: external\n  webhook_configs:\n  - url: https://example.invalid/notify\n'}}
        with self.assertRaisesRegex(ValueError, 'External'):
            observer.exercise('http://prometheus', 'http://alertmanager')
        observer.kube.assert_not_called()

    def test_probe_owned_by_another_manager_is_not_modified(self):
        observer = self.observer()
        observer.kube.return_value = {'metadata': {'labels': {'app.kubernetes.io/managed-by': 'someone-else'}}}
        with self.assertRaisesRegex(ValueError, 'another manager'):
            observer.exercise('http://prometheus', 'http://alertmanager')
        self.assertEqual(observer.kube.call_count, 1)
