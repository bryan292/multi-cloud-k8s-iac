"""Validate cloud identity and state destination before invoking Terraform."""
import hashlib
import json
import os
import subprocess
from pathlib import Path


def cloud_environment(config):
    env = dict(os.environ)
    env['TG_DISABLE_BUCKET_UPDATE'] = 'true'
    env['TG_BACKEND_REQUIRE_BOOTSTRAP'] = 'true'
    # These flags can silently override variables, backend settings, or state files.
    if any(value and (key == 'TF_CLI_ARGS' or key.startswith('TF_CLI_ARGS_') or
                      key.startswith('TF_VAR_') or key in {'TF_DATA_DIR', 'TG_CONFIG', 'TG_SOURCE',
                      'TG_AUTH_PROVIDER_CMD', 'TG_IAM_ASSUME_ROLE', 'TG_DOWNLOAD_DIR',
                      'TG_SOURCE_MAP', 'TG_TF_PATH', 'TG_IAM_ASSUME_ROLE_WEB_IDENTITY_TOKEN'}) for key, value in env.items()):
        raise ValueError('environment: remove Terraform/Terragrunt configuration overrides before running the orchestrator')
    if config['global']['provider'] == 'aws':
        for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
                    'AWS_SECURITY_TOKEN', 'AWS_ROLE_ARN', 'AWS_WEB_IDENTITY_TOKEN_FILE'):
            env.pop(key, None)
        env['AWS_PROFILE'] = config['aws']['profile']
        env['AWS_DEFAULT_PROFILE'] = config['aws']['profile']
        env['AWS_REGION'] = env['AWS_DEFAULT_REGION'] = config['aws']['region']
        env['AWS_PAGER'] = ''
    else:
        # v1 supports the Azure CLI login; do not let the provider select another identity.
        for key in list(env):
            if key.startswith('ARM_') or key.startswith('AZURE_STORAGE_'):
                env.pop(key)
        env.update(ARM_USE_CLI='true', ARM_USE_MSI='false', ARM_USE_OIDC='false',
                   ARM_SUBSCRIPTION_ID=config['azure']['subscription_id'],
                   ARM_TENANT_ID=config['azure']['tenant_id'])
    return env


def command_json(*args, env=None):
    try:
        result = subprocess.run(args, text=True, capture_output=True, check=True,
                                timeout=90, env=env)
        return json.loads(result.stdout or '{}')
    except (OSError, subprocess.SubprocessError, ValueError):
        # CLI stderr and command arguments may include identifiers or credentials.
        raise ValueError(f'{args[0]}: cloud check failed; verify login, permissions and configured destination') from None


def check_identity(config, env):
    if config['global']['provider'] == 'aws':
        a = config['aws']
        identity = command_json('aws', '--profile', a['profile'], 'sts', 'get-caller-identity',
                                '--output', 'json', env=env)
        if identity.get('Account') != a['account_id']:
            raise ValueError('aws.account_id: active account differs; select the configured profile/account')
        arn = identity.get('Arn', '')
        if arn.endswith(':root') or not arn:
            raise ValueError('aws.profile: use an IAM role/user; root credentials are not supported')
        return identity
    a = config['azure']
    account = command_json('az', 'account', 'show', '--output', 'json', env=env)
    if (str(account.get('id', '')).lower() != a['subscription_id'].lower() or
            str(account.get('tenantId', '')).lower() != a['tenant_id'].lower()):
        raise ValueError('azure.subscription_id/tenant_id: active login differs; select the configured subscription and tenant')
    return account


def check_backend(config, env):
    if config['global']['provider'] == 'aws':
        a = config['aws']
        base = ['aws', '--profile', a['profile'], '--region', a['state_region'], 's3api']
        options = ['--bucket', a['bucket_name'], '--expected-bucket-owner', a['account_id'], '--output', 'json']
        command_json(*base, 'head-bucket', *options, env=env)
        location = command_json(*base, 'get-bucket-location', *options, env=env).get('LocationConstraint')
        region = {'EU': 'eu-west-1', None: 'us-east-1'}.get(location, location)
        if region != a['state_region']:
            raise ValueError('aws.state_region: backend region differs; restore the existing bucket location')
    else:
        a, s = config['azure'], config['azure']['state']
        account = command_json('az', 'storage', 'account', 'show', '--subscription', a['subscription_id'],
                               '--resource-group', s['resource_group_name'], '--name', s['storage_account_name'],
                               '--output', 'json', env=env)
        expected = f"/subscriptions/{a['subscription_id']}/resourceGroups/{s['resource_group_name']}/providers/Microsoft.Storage/storageAccounts/{s['storage_account_name']}"
        if str(account.get('id', '')).lower() != expected.lower():
            raise ValueError('azure.state: storage account differs from the configured subscription/resource group')
        container = command_json('az', 'storage', 'container', 'exists', '--account-name', s['storage_account_name'],
                                 '--name', s['container_name'], '--auth-mode', 'login', '--output', 'json', env=env)
        if container.get('exists') is not True:
            raise ValueError('azure.state.container_name: backend container missing or inaccessible; run bootstrap or restore configuration')


def backend_config(config, stage):
    g = config['global']
    key = f"{g['cluster_name']}/{g['environment']}/{stage}/terraform.tfstate"
    if g['provider'] == 'aws':
        a = config['aws']
        return 's3', {'bucket': a['bucket_name'], 'region': a['state_region'], 'key': '~' + key,
                      'allowed_account_ids': [a['account_id']]}
    a, s = config['azure'], config['azure']['state']
    return 'azurerm', {**s, 'subscription_id': a['subscription_id'], 'tenant_id': a['tenant_id'], 'key': key}


def check_cached_backends(config, root, stages):
    for stage in stages:
        directory = Path(root) / 'deployment-config' / stage
        expected_type, expected = backend_config(config, stage)
        for metadata in directory.glob('**/.terraform/terraform.tfstate'):
            try:
                backend = json.loads(metadata.read_text()).get('backend')
            except (ValueError, OSError):
                raise ValueError('backend: unreadable local metadata; inspect the initialized Terraform cache') from None
            if not backend:
                continue
            # A shared stage can have separate AWS and Azure caches. Different backend
            # types are safe to reinitialize, but never migrate their state automatically.
            if backend.get('type') != expected_type:
                continue
            actual = backend.get('config', {})
            if any(actual.get(key) != value for key, value in expected.items()):
                raise ValueError(f'backend.{stage}: initialized destination differs; inspect cached state before changing configuration')


def pin_target(config, root, stages):
    g = config['global']
    directory = Path(root) / '.deployment-targets'
    identifier = hashlib.sha256(json.dumps([g['provider'], g['cluster_name'], g['environment'], 'bootstrap' if stages == ['bootstrap'] else 'deployment']).encode()).hexdigest()
    path = directory / f'{identifier}.json'
    target = {stage: backend_config(config, stage) for stage in stages}
    serialized = json.dumps(target, sort_keys=True, indent=2) + '\n'
    directory.mkdir(mode=0o700, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_text() != serialized:
            raise ValueError('backend: destination differs from the previously verified target; restore configuration or perform a reviewed state migration') from None
    else:
        with os.fdopen(fd, 'w') as stream:
            stream.write(serialized)


def check_bootstrap_arguments(arguments):
    if not arguments or arguments[0] not in {'init', 'plan', 'apply', 'destroy', 'validate', 'output', 'show'}:
        raise ValueError('bootstrap.action: choose init, plan, apply, destroy, validate, output or show')
    forbidden = {'-var', '-var-file', '-backend-config', '-state', '-state-out', '-chdir', '-migrate-state', '-force-copy'}
    if any(argument.split('=', 1)[0] in forbidden for argument in arguments[1:]):
        raise ValueError('bootstrap.arguments: configure identity/backend through config.yaml; state and variable overrides are not supported')
    if arguments[0] == 'apply' and any(not argument.startswith('-') for argument in arguments[1:]):
        raise ValueError('bootstrap.arguments: saved plans cannot be verified by this wrapper; use an interactive apply from the validated configuration')


def pre_plan(config, root, stages):
    env = cloud_environment(config)
    check_cached_backends(config, root, stages)
    check_identity(config, env)
    check_backend(config, env)
    pin_target(config, root, stages)
    return env


def check_bootstrap_state(config, directory):
    path = Path(directory) / 'terraform.tfstate'
    if not path.exists():
        return False
    has_backend = False
    try:
        state = json.loads(path.read_text())
        for resource in state.get('resources', []):
            for instance in resource.get('instances', []):
                attributes = instance.get('attributes', {})
                if config['global']['provider'] == 'aws':
                    a = config['aws']
                    has_backend = has_backend or resource['type'] == 'aws_s3_bucket'
                    if resource['type'] == 'aws_s3_bucket' and (attributes.get('bucket') != a['bucket_name'] or attributes.get('region') != a['state_region']):
                        raise ValueError()
                else:
                    has_backend = has_backend or resource['type'] == 'azurerm_storage_container'
                    a, s = config['azure'], config['azure']['state']
                    expected = {'azurerm_resource_group': s['resource_group_name'],
                                'azurerm_storage_account': s['storage_account_name'],
                                'azurerm_storage_container': s['container_name']}
                    if resource['type'] in expected and attributes.get('name') != expected[resource['type']]:
                        raise ValueError()
                    resource_id = attributes.get('id', '').lower()
                    if resource_id.startswith('/subscriptions/') and not resource_id.startswith(f"/subscriptions/{a['subscription_id'].lower()}/"):
                        raise ValueError()
    except (ValueError, KeyError, TypeError, OSError):
        raise ValueError('bootstrap.state: existing local state differs or is unreadable; restore the original destination before planning') from None
    return has_backend


def read_remote_state(config, stage, env):
    """Read a deployment state without evaluating dependencies of a removed cluster."""
    import tempfile
    _, backend = backend_config(config, stage)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'state.json'
        if config['global']['provider'] == 'aws':
            a = config['aws']
            command_json('aws', '--profile', a['profile'], '--region', a['state_region'],
                         's3api', 'get-object', '--bucket', a['bucket_name'], '--key', backend['key'],
                         '--expected-bucket-owner', a['account_id'], str(path), '--output', 'json', env=env)
        else:
            state = config['azure']['state']
            command_json('az', 'storage', 'blob', 'download', '--account-name', state['storage_account_name'],
                         '--container-name', state['container_name'], '--name', backend['key'], '--file', str(path),
                         '--overwrite', '--auth-mode', 'login', '--output', 'json', env=env)
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or not isinstance(value.get('resources', []), list):
                raise ValueError()
            return value
        except (ValueError, OSError):
            raise ValueError('backend: cannot validate remote state; inspect the selected state before resuming') from None
