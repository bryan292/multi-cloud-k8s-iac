#!/usr/bin/env python3
"""Exercise an isolated AKS LoadBalancer service and cert-manager certificate."""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import yaml
from config import load_config
from target import cloud_environment


def main():
    root = Path(__file__).resolve().parents[1]
    config = load_config(os.environ.get('IAC_CONFIG', root / 'config.yaml'))
    if config['global']['provider'] != 'azure':
        raise ValueError('global.provider: this test requires Azure; use smoke-ingress.py for AWS')
    ranges = config['azure']['network']['api_server_authorized_ip_ranges']
    if not ranges:
        raise ValueError('azure.network.api_server_authorized_ip_ranges: this external HTTP test requires a trusted client CIDR')
    env = cloud_environment(config)
    env.setdefault('KUBECONFIG', str(root / 'kubeconfig.yaml'))
    name = 'iac-service-smoke-' + uuid.uuid4().hex[:10]

    def kube(*args, input=None):
        return subprocess.check_output(['kubectl', *args], input=input, text=True, env=env)

    metadata = {'name': name, 'namespace': name}
    objects = [
        {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': name}},
        {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': metadata, 'spec': {
            'replicas': 1, 'selector': {'matchLabels': {'app': name}},
            'template': {'metadata': {'labels': {'app': name}}, 'spec': {
                'securityContext': {'runAsNonRoot': True, 'runAsUser': 1000, 'seccompProfile': {'type': 'RuntimeDefault'}},
                'containers': [{'name': 'echo', 'image': 'hashicorp/http-echo:1.0.0',
                                'args': ['-listen=:8080', '-text=iac-smoke-ok'],
                                'ports': [{'containerPort': 8080}],
                                'readinessProbe': {'httpGet': {'path': '/', 'port': 8080}},
                                'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                                'resources': {'requests': {'cpu': '10m', 'memory': '16Mi'}, 'limits': {'cpu': '100m', 'memory': '32Mi'}}}]
            }}
        }},
        {'apiVersion': 'v1', 'kind': 'Service', 'metadata': metadata, 'spec': {
            'type': 'LoadBalancer', 'loadBalancerSourceRanges': ranges,
            'selector': {'app': name}, 'ports': [{'port': 80, 'targetPort': 8080}]}},
        {'apiVersion': 'cert-manager.io/v1', 'kind': 'Issuer', 'metadata': metadata, 'spec': {'selfSigned': {}}},
        {'apiVersion': 'cert-manager.io/v1', 'kind': 'Certificate', 'metadata': metadata, 'spec': {
            'secretName': name, 'dnsNames': [name + '.example.test'], 'issuerRef': {'name': name, 'kind': 'Issuer'}}},
    ]
    try:
        kube('apply', '-f', '-', input=yaml.safe_dump_all(objects))
        kube('wait', '-n', name, 'deployment/' + name, '--for=condition=Available', '--timeout=300s')
        kube('wait', '-n', name, 'certificate/' + name, '--for=condition=Ready', '--timeout=180s')
        print('PASS AKS cert-manager issued a self-signed certificate', flush=True)
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            service = json.loads(kube('get', 'service', name, '-n', name, '-o', 'json'))
            ingress = service.get('status', {}).get('loadBalancer', {}).get('ingress', [])
            if ingress and ingress[0].get('ip'):
                try:
                    with urllib.request.urlopen('http://' + ingress[0]['ip'], timeout=10) as response:
                        if response.status == 200 and response.read().strip() == b'iac-smoke-ok':
                            print('PASS HTTP through AKS LoadBalancer to pod (trusted CIDRs only)', flush=True)
                            return
                except (urllib.error.URLError, TimeoutError):
                    pass
            time.sleep(10)
        raise RuntimeError('AKS LoadBalancer HTTP test timed out')
    finally:
        kube('delete', 'namespace', name, '--ignore-not-found', '--wait=true', '--timeout=600s')
        print('Removed isolated AKS test namespace and requested service/IP cleanup', flush=True)


if __name__ == '__main__':
    main()
