"""Export only the public, expected workload identity binding fields from cloud state."""
import re

try:
    from .target import cloud_environment, check_identity, check_backend, read_remote_state
except ImportError:
    from target import cloud_environment, check_identity, check_backend, read_remote_state


def bindings(config, state):
    configured = config.get('workload_identities', {})
    actual = state.get('outputs', {}).get('workload_identity_bindings', {}).get('value', {})
    if not isinstance(actual, dict) or set(configured) != set(actual):
        raise ValueError('workload identities differ from deployed state; review and apply the cluster stage first')
    result = {}
    provider = config['global']['provider']
    for key, identity in configured.items():
        try:
            source = actual[key]
            metadata = source['service_account']['metadata']
            subject = f"system:serviceaccount:{identity['namespace']}:{identity['service_account']}"
            if (source['provider'] != provider or source['subject'] != subject or
                    metadata['namespace'] != identity['namespace'] or metadata['name'] != identity['service_account']):
                raise ValueError()
            if provider == 'aws':
                arn = metadata['annotations']['eks.amazonaws.com/role-arn']
                if not re.fullmatch(r'arn:aws:iam::' + config['aws']['account_id'] + r':role/[A-Za-z0-9+=,.@_/-]+', arn):
                    raise ValueError()
                annotations = {'eks.amazonaws.com/role-arn': arn}
                labels, audience = {}, 'sts.amazonaws.com'
            else:
                client = metadata['annotations']['azure.workload.identity/client-id']
                if not re.fullmatch(r'[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', client):
                    raise ValueError()
                annotations = {'azure.workload.identity/client-id': client,
                               'azure.workload.identity/tenant-id': config['azure']['tenant_id']}
                labels, audience = {'azure.workload.identity/use': 'true'}, 'api://AzureADTokenExchange'
            result[key] = {
                'provider': provider, 'audience': audience, 'subject': subject,
                'service_account': {'apiVersion': 'v1', 'kind': 'ServiceAccount',
                    'metadata': {'name': identity['service_account'], 'namespace': identity['namespace'],
                                 'annotations': annotations}, 'automountServiceAccountToken': False},
                'pod_labels': labels,
            }
        except (KeyError, TypeError, ValueError):
            raise ValueError('deployed workload identity binding is invalid or belongs to another destination') from None
    return result


def export(config):
    env = cloud_environment(config)
    check_identity(config, env)
    check_backend(config, env)
    stage = 'aws/eks' if config['global']['provider'] == 'aws' else 'azure/aks'
    return bindings(config, read_remote_state(config, stage, env))
