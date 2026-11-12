"""Bounded, redacted, read-only platform diagnostics (SPEC-009)."""
import json
import re
import shutil
import subprocess
from decimal import Decimal

try:
    from .target import cloud_environment, check_identity, check_backend
except ImportError:
    from target import cloud_environment, check_identity, check_backend


def quantity(value):
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))([eE][+-]?\d+|[KMGTPE]i|[kMGTPEmun])?', str(value))
    if not match:
        raise ValueError('invalid resource quantity')
    number, suffix = match.groups()
    factors = {'': 1, 'm': Decimal('0.001'), 'u': Decimal('0.000001'), 'n': Decimal('0.000000001')}
    factors.update({unit: Decimal(1000) ** (index + 1) for index, unit in enumerate('kMGTPE')})
    factors.update({unit + 'i': Decimal(1024) ** (index + 1) for index, unit in enumerate('KMGTPE')})
    factor = Decimal(10) ** int(suffix[1:]) if suffix and re.fullmatch(r'[eE][+-]?\d+', suffix) else factors[suffix or '']
    return Decimal(number) * factor


def ready(item, generation=False):
    status = item.get('status', {})
    if generation and (not isinstance(item.get('metadata', {}).get('generation'), int) or item['metadata']['generation'] < 1):
        return False
    return any(c.get('type') == 'Ready' and c.get('status') == 'True' and
               (not generation or c.get('observedGeneration', status.get('observedGeneration')) == item['metadata'].get('generation'))
               for c in status.get('conditions', []))


def readiness(items, optional=False, generation=False):
    good = sum(ready(item, generation) for item in items)
    return {'status': 'passed' if (items or optional) and good == len(items) else 'failed',
            'count': len(items), 'ready': good, 'detail': 'not_configured' if not items and optional else 'readiness'}


class Client:
    def __init__(self, env):
        self.env = env

    def get(self, *args, raw=False):
        command = ['kubectl', 'get', *args] + ([] if raw else ['-o', 'json'])
        try:
            response = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=30, check=True)
            data = json.loads(response.stdout)
            if not isinstance(data, dict):
                raise ValueError()
            if not raw and not isinstance(data.get('items'), list):
                raise ValueError()
            return data if raw else data['items']
        except (OSError, subprocess.SubprocessError, ValueError):
            raise ValueError('query_failed') from None


def diagnose(operation, emit, offline=False):
    results = []
    def record(check, **result):
        row = {'check': check, **result}
        results.append(row)
        emit(event='diagnostic', **row)
        return result.get('status') == 'passed'
    def check(name, fn, hint):
        try:
            result = fn()
        except (ValueError, KeyError, TypeError, ArithmeticError):
            result = {'status': 'failed', 'detail': 'query_or_response_failed'}
        if result['status'] != 'passed':
            result['hint'] = hint
        record(name, **result)
        return result['status'] == 'passed'
    def finish():
        failed = sum(row['status'] == 'failed' for row in results)
        warnings = sum(row['status'] == 'warning' for row in results)
        emit(event='diagnostic_summary', failed=failed, warnings=warnings, checks=len(results), offline=offline)
        return int(failed > 0)

    record('configuration', status='passed')
    required = ['terraform', 'terragrunt', 'kubectl', 'helm'] + (['aws'] if operation.provider == 'aws' else ['az', 'kubelogin'])
    for tool in required:
        record('tool:' + tool, status='passed' if shutil.which(tool) else 'failed')
    if offline:
        return finish()
    env = cloud_environment(operation.config)
    try:
        check_identity(operation.config, env)
        record('identity', status='passed')
    except ValueError:
        record('identity', status='failed', hint='Verify login and the configured account/subscription; no further requests were made.')
        record('backend', status='skipped', detail='identity_failed')
        record('kubernetes', status='skipped', detail='identity_failed')
        return finish()
    try:
        check_backend(operation.config, env)
        record('backend', status='passed')
    except ValueError:
        record('backend', status='failed', hint='Verify backend existence, login permissions and the configured state destination.')
    kubeconfig = operation.target_dir / 'kubeconfig.yaml'
    if not kubeconfig.is_file():
        record('kubernetes', status='failed', hint='Generate the selected target kubeconfig; no cluster requests were made.')
        return finish()
    env['KUBECONFIG'] = str(kubeconfig)
    client = Client(env)
    if not check('api', lambda: {'status': 'passed' if client.get('--raw', '/version', raw=True).get('gitVersion') else 'failed'},
                 'Check cluster API connectivity, TLS and Kubernetes authentication.'):
        record('cluster_checks', status='skipped', detail='api_failed')
        return finish()
    def cluster_identity():
        settings = client.get('--raw', '/api/v1/namespaces/flux-system/configmaps/cluster-settings', raw=True)['data']
        global_config = operation.config['global']
        expected = f"{global_config['environment']}-{global_config['cluster_name']}-cluster"
        return {'status': 'passed' if settings.get('cluster_name') == expected and settings.get('provider') == operation.provider else 'failed'}
    if not check('cluster_identity', cluster_identity, 'The selected kubeconfig must match the managed cluster-settings ConfigMap.'):
        record('cluster_checks', status='skipped', detail='cluster_identity_failed')
        return finish()
    nodes = []
    def check_nodes():
        nodes.extend(client.get('nodes'))
        minimum = (operation.config['eks'] if operation.provider == 'aws' else operation.config['azure'])[
            'node_scaling' if operation.provider == 'aws' else 'node_pool']['min']
        summary = readiness(nodes)
        if len(nodes) < minimum:
            summary['status'] = 'failed'
        return summary
    check('nodes', check_nodes, 'Inspect node readiness, node-pool capacity and scheduling pressure.')
    node_names = {n['metadata']['name'] for n in nodes}
    for resource in ('gitrepositories', 'kustomizations', 'helmreleases'):
        check('flux:' + resource, lambda r=resource: readiness(client.get(r, '-n', 'flux-system'), generation=True),
              'Inspect Flux conditions and source revisions; a stale observed generation is not Ready.')
    def metrics():
        items = client.get('--raw', '/apis/metrics.k8s.io/v1beta1/nodes', raw=True)['items']
        covered = {n['metadata']['name'] for n in items if n.get('usage', {}).get('cpu') and n.get('usage', {}).get('memory')}
        return {'status': 'passed' if node_names and node_names <= covered else 'failed', 'nodes_with_metrics': len(covered)}
    check('metrics', metrics, 'Inspect metrics-server and the aggregated metrics API; all known nodes need CPU/memory samples.')
    def csi():
        driver = 'ebs.csi.aws.com' if operation.provider == 'aws' else 'disk.csi.azure.com'
        registered = {d['metadata']['name'] for d in client.get('csidrivers')}
        covered = {n['metadata']['name'] for n in client.get('csinodes') if any(d['name'] == driver for d in n['spec']['drivers'])}
        return {'status': 'passed' if driver in registered and node_names and node_names <= covered else 'failed',
                'driver': driver, 'nodes_with_driver': len(covered)}
    check('csi', csi, 'Inspect the provider CSI controller/node DaemonSet; registration does not prove a new volume can be provisioned.')
    def dns():
        deployments = client.get('deployments', '-n', 'kube-system', '-l', 'k8s-app=kube-dns')
        healthy = bool(deployments) and all(d['status'].get('observedGeneration', 0) >= d['metadata']['generation'] and
            d['status'].get('availableReplicas', 0) >= d['spec'].get('replicas', 1) > 0 for d in deployments)
        slices = client.get('endpointslices', '-n', 'kube-system', '-l', 'kubernetes.io/service-name=kube-dns')
        addresses = sum(len(e.get('addresses', [])) for s in slices for e in s.get('endpoints', []) if e.get('conditions', {}).get('ready', True))
        return {'status': 'passed' if healthy and addresses else 'failed', 'ready_endpoints': addresses,
                'detail': 'controller_and_endpoints_only'}
    check('dns', dns, 'Inspect CoreDNS and kube-dns EndpointSlices; this check does not issue a DNS query from a workload.')
    for resource in ('certificates', 'issuers', 'clusterissuers'):
        check('certificates:' + resource, lambda r=resource: readiness(client.get(r, '-A'), optional=True),
              'Inspect cert-manager conditions and renewal; no certificate/private-key Secret is read.')
    def ingress():
        items = client.get('ingresses', '-A')
        pending = sum(not i.get('status', {}).get('loadBalancer', {}).get('ingress') for i in items)
        return {'status': 'warning' if pending else 'passed', 'count': len(items), 'address_pending': pending,
                'detail': 'not_configured' if not items else 'status_only_no_http_probe'}
    check('ingress', ingress, 'Inspect the ingress class/controller and address allocation; no HTTP or TLS probe is performed.')
    def quotas():
        items = client.get('resourcequotas', '-A')
        exhausted = 0
        for item in items:
            hard = item['status']['hard']
            used = item['status']['used']
            for resource, limit in hard.items():
                if resource not in used:
                    raise ValueError('quota_usage_missing')
                exhausted += quantity(used[resource]) >= quantity(limit)
        return {'status': 'warning' if exhausted else 'passed', 'count': len(items), 'limits_at_capacity': exhausted,
                'detail': 'not_configured' if not items else 'kubernetes_quota_only'}
    check('quotas', quotas, 'Review namespace quota usage and intended limits, including deliberate zero limits; cloud billing quotas are not checked.')
    return finish()
