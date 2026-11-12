"""DIA-001..006: offline, authorization, stale state, resource coverage and redaction."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import diagnostics as d
from scripts.config import load_config


def ready(name):
    return {'metadata': {'name': name, 'generation': 1}, 'status': {
        'conditions': [{'type': 'Ready', 'status': 'True', 'observedGeneration': 1}]}}


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.config = load_config('config.aws.yaml_example')
        self.operation = SimpleNamespace(config=self.config, provider='aws', target_dir=Path(self.temp.name))
        (self.operation.target_dir / 'kubeconfig.yaml').write_text('private fixture')
        self.events, self.calls = [], []
        self.data = {
            '/version': {'gitVersion': 'v1.35.0'},
            '/api/v1/namespaces/flux-system/configmaps/cluster-settings': {'data': {
                'cluster_name': f"{self.config['global']['environment']}-{self.config['global']['cluster_name']}-cluster", 'provider': 'aws'}},
            'nodes': [ready('node-1'), ready('node-2')],
            'gitrepositories': [ready('source')], 'helmreleases': [ready('monitoring')], 'kustomizations': [ready('platform')],
            '/apis/metrics.k8s.io/v1beta1/nodes': {'items': [dict(metadata={'name': n}, usage={'cpu': '10m', 'memory': '100Mi'}) for n in ('node-1','node-2')]},
            'csidrivers': [{'metadata': {'name': 'ebs.csi.aws.com'}}, {'metadata': {'name': 'disk.csi.azure.com'}}],
            'csinodes': [{'metadata': {'name': n}, 'spec': {'drivers': [{'name': 'ebs.csi.aws.com'}, {'name': 'disk.csi.azure.com'}]}} for n in ('node-1','node-2')],
            'deployments': [{'metadata': {'generation': 1}, 'spec': {'replicas': 2}, 'status': {'observedGeneration': 1, 'availableReplicas': 2}}],
            'endpointslices': [{'endpoints': [{'addresses': ['10.0.0.1'], 'conditions': {'ready': True}}]}],
            'certificates': [], 'issuers': [], 'clusterissuers': [], 'ingresses': [], 'resourcequotas': [],
        }
        self.identity = patch.object(d, 'check_identity').start(); self.addCleanup(patch.stopall)
        self.backend = patch.object(d, 'check_backend').start()
        self.environment = patch.object(d, 'cloud_environment', return_value={}).start()
        patch.object(d.shutil, 'which', return_value='/bin/tool').start()
        patch.object(d.subprocess, 'run', side_effect=self.run_command).start()

    def run_command(self, args, **kwargs):
        self.calls.append(args)
        self.assertEqual(args[:2], ['kubectl','get'])
        self.assertNotIn('secrets', args)
        self.assertEqual(kwargs['timeout'], 30)
        self.assertEqual(kwargs['env']['KUBECONFIG'], str(self.operation.target_dir / 'kubeconfig.yaml'))
        key = args[3] if args[2] == '--raw' else args[2]
        value = self.data[key]
        if isinstance(value, Exception): raise value
        return SimpleNamespace(stdout=json.dumps(value if args[2] == '--raw' else {'items': value}))

    def diagnose(self, offline=False):
        return d.diagnose(self.operation, lambda **e:self.events.append(e), offline)

    def status(self, name):
        return next(e['status'] for e in self.events if e.get('check') == name)

    def test_healthy_platform_and_absent_optional_resources(self):
        self.assertEqual(self.diagnose(),0)
        self.assertEqual(self.status('csi'),'passed')
        self.assertEqual(self.status('dns'),'passed')
        self.assertTrue(any(e.get('detail') == 'not_configured' for e in self.events))
        self.assertGreater(len(self.calls),10)

    def test_azure_uses_azure_driver(self):
        c=load_config('config.azure.yaml_example');self.operation.config=c;self.operation.provider='azure'
        self.data['/api/v1/namespaces/flux-system/configmaps/cluster-settings']['data']={
            'cluster_name':f"{c['global']['environment']}-{c['global']['cluster_name']}-cluster",'provider':'azure'}
        self.assertEqual(self.diagnose(),0)
        self.assertTrue(any(e.get('driver')=='disk.csi.azure.com' for e in self.events))

    def test_offline_has_no_cloud_or_kubernetes_requests(self):
        self.assertEqual(self.diagnose(True),0)
        self.environment.assert_not_called();self.identity.assert_not_called();self.backend.assert_not_called()
        self.assertEqual(self.calls,[])

    def test_wrong_cloud_identity_stops_other_requests(self):
        self.identity.side_effect=ValueError('SECRET_SENTINEL')
        self.assertEqual(self.diagnose(),1)
        self.backend.assert_not_called();self.assertEqual(self.calls,[])
        self.assertNotIn('SECRET_SENTINEL',str(self.events))

    def test_wrong_cluster_stops_resource_inventory(self):
        self.data['/api/v1/namespaces/flux-system/configmaps/cluster-settings']['data']['cluster_name']='other'
        self.assertEqual(self.diagnose(),1)
        self.assertEqual(self.status('cluster_identity'),'failed')
        self.assertEqual(len(self.calls),2)

    def test_timeout_and_forbidden_are_redacted_failures_not_absence(self):
        for error in (subprocess.TimeoutExpired(['kubectl'],30,output='SECRET_SENTINEL'), subprocess.CalledProcessError(1,['kubectl'],stderr='SECRET_SENTINEL')):
            with self.subTest(error=type(error).__name__):
                self.events=[];self.data['certificates']=error
                self.assertEqual(self.diagnose(),1)
                self.assertEqual(self.status('certificates:certificates'),'failed')
                self.assertNotIn('SECRET_SENTINEL',str(self.events))
                self.assertEqual(self.status('quotas'),'passed')

    def test_stale_flux_generation_missing_csi_metrics_and_dns_fail(self):
        self.data['helmreleases'][0]['status']['conditions'][0]['observedGeneration']=0
        self.data['csinodes']=self.data['csinodes'][:1]
        self.data['/apis/metrics.k8s.io/v1beta1/nodes']['items']=[]
        self.data['endpointslices'][0]['endpoints'][0]['conditions']['ready']=False
        self.assertEqual(self.diagnose(),1)
        for check in ('flux:helmreleases','csi','metrics','dns'):self.assertEqual(self.status(check),'failed')

    def test_quota_equivalent_units_are_reported_at_capacity(self):
        self.data['resourcequotas']=[{'status': {'hard': {'cpu':'1','memory':'1Gi'},'used':{'cpu':'1000m','memory':'1024Mi'}}}]
        self.assertEqual(self.diagnose(),0)
        result=next(e for e in self.events if e.get('check')=='quotas')
        self.assertEqual(result['status'],'warning');self.assertEqual(result['limits_at_capacity'],2)

    def test_quantity_formats_and_invalid_input(self):
        self.assertEqual(d.quantity('1e3'),d.quantity('1k'))
        self.assertEqual(d.quantity('1.5Gi'),d.quantity('1536Mi'))
        for value in ('NaN','secret','1foo'):
            with self.assertRaises(ValueError): d.quantity(value)
        self.assertFalse(d.ready({'metadata':{},'status':{'conditions':[{'type':'Ready','status':'True'}]}},generation=True))

    def test_missing_kubeconfig_stops_cluster_requests(self):
        (self.operation.target_dir / 'kubeconfig.yaml').unlink()
        self.assertEqual(self.diagnose(),1)
        self.assertEqual(self.status('kubernetes'),'failed')
        self.assertEqual(self.calls,[])

    def test_unavailable_api_stops_resource_requests(self):
        self.data['/version']=subprocess.CalledProcessError(1,['kubectl'],stderr='SECRET_SENTINEL')
        self.assertEqual(self.diagnose(),1)
        self.assertEqual(self.status('api'),'failed')
        self.assertEqual(len(self.calls),1)
        self.assertNotIn('SECRET_SENTINEL',str(self.events))
