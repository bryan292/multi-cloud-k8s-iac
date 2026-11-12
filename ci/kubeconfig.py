#!/usr/bin/env python3
"""Recreate a private kubeconfig on a fresh CI runner for existing cluster stages."""
import os
from urllib.parse import urlsplit
import yaml
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.operations import Operations
from scripts.target import cloud_environment, check_identity


def use_tunnel(path):
    data = yaml.safe_load(path.read_text())
    context = next(item['context'] for item in data['contexts'] if item['name'] == data['current-context'])
    cluster = next(item['cluster'] for item in data['clusters'] if item['name'] == context['cluster'])
    endpoint = urlsplit(cluster['server'])
    if (endpoint.scheme != 'https' or not endpoint.hostname or endpoint.port not in (None, 443)
            or endpoint.username or endpoint.password or endpoint.path not in ('', '/')
            or endpoint.query or endpoint.fragment or cluster.get('insecure-skip-tls-verify')
            or not cluster.get('certificate-authority-data') or cluster.get('proxy-url')):
        raise ValueError('tunnel requires a CA-verified HTTPS Kubernetes endpoint on port 443')
    cluster['tls-server-name'] = endpoint.hostname
    cluster['server'] = 'https://127.0.0.1:8443'
    path.write_text(yaml.safe_dump(data))
    path.chmod(0o600)


def prepare(config):
    operation = Operations(ROOT, config)
    env = cloud_environment(operation.config)
    check_identity(operation.config, env)
    path = operation.target_dir / 'kubeconfig.yaml'
    global_config = operation.config['global']
    name = f"{global_config['environment']}-{global_config['cluster_name']}-cluster"
    if operation.provider == 'aws':
        args = ['aws', 'eks', 'update-kubeconfig', '--name', name, '--kubeconfig', str(path)]
    else:
        azure = operation.config['azure']
        args = ['az', 'aks', 'get-credentials', '--resource-group', azure['resource_group_name'],
                '--name', name, '--file', str(path), '--overwrite-existing']
    subprocess.run(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    path.chmod(0o600)
    if operation.provider == 'azure':
        subprocess.run(['kubelogin', 'convert-kubeconfig', '-l', 'azurecli', '--kubeconfig', str(path)],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.environ.get('IAC_TUNNEL') == 'true':
        use_tunnel(path)


if __name__ == '__main__':
    try:
        prepare(sys.argv[1])
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        print('could not prepare cluster access for the selected destination', file=sys.stderr)
        raise SystemExit(1)
