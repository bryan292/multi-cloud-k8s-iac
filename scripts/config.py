"""Offline v1 configuration contract shared by operational entry points."""
import ipaddress
import json
import re
from urllib.parse import urlsplit
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schemas/config-v1.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def load_config(path):
    try:
        value = parse_yaml(Path(path).read_text())
    except (yaml.YAMLError, UnicodeError):
        raise ValueError("config: expected valid UTF-8 YAML; check syntax") from None
    return validate(value)


class StrictLoader(yaml.SafeLoader):
    """Do not silently accept repeated configuration fields or merge overrides."""


def unique_mapping(loader, node, deep=False):
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in keys:
            raise ValueError("config: use unique string field names; duplicate YAML keys are not allowed")
        keys.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def parse_yaml(text):
    try:
        return yaml.load(text, Loader=StrictLoader)
    except (yaml.YAMLError, UnicodeError, RecursionError):
        raise ValueError("config: expected valid YAML without recursive aliases or merge overrides") from None


def validate(value):
    error = next(VALIDATOR.iter_errors(value), None)
    if error is not None:
        # Never include instance values or jsonschema's raw message (may contain secrets).
        field = ".".join(str(part) for part in error.absolute_path) or "config"
        correction = {
            'required': 'add the required fields',
            'additionalProperties': 'remove unknown fields',
            'type': f'use the expected {error.validator_value} type',
            'enum': 'choose a supported value',
            'const': 'use schema_version: 1; migrate historical files with migrate-config.py',
            'pattern': 'use the documented field format',
            'format': 'use the documented field format',
        }.get(error.validator, 'use the documented field limits')
        if error.validator == 'required' and isinstance(error.instance, dict):
            missing = [key for key in error.validator_value if key not in error.instance]
            correction = 'add required fields: ' + ', '.join(missing)
        raise ValueError(f"{field}: {correction}; see schemas/config-v1.json")
    validate_semantics(value)
    return value


def network(value, field):
    try:
        return ipaddress.ip_network(value)
    except ValueError:
        raise ValueError(f"{field}: expected a valid network CIDR with no host bits") from None


def administrative_cidrs(values, field):
    for index, value in enumerate(values):
        cidr = network(value, f"{field}.{index}")
        if cidr.version != 4 or cidr.prefixlen == 0:
            raise ValueError(f"{field}.{index}: use a restricted IPv4 administrative CIDR instead of /0")


def scaling(value, field):
    if not 2 <= value["min"] <= value["desired"] <= value["max"]:
        raise ValueError(f"{field}: require 2 <= min <= desired <= max")


def validate_semantics(config):
    for block in ('platform', 'application'):
        repository = config[block]['repository']
        if repository:
            try:
                url = urlsplit(repository)
                valid = url.scheme == 'https' and url.hostname and not (url.username or url.password or url.query or url.fragment)
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(f"{block}.repository: use HTTPS without credentials, query parameters or fragments")
    validate_workload_identities(config)
    g = config['global']
    if g['provider'] == 'azure' and len(f"{g['environment']}-{g['cluster_name']}-cluster-logs") > 63:
        raise ValueError('global.cluster_name/environment: generated AKS Log Analytics workspace name must be at most 63 characters')
    if config["global"]["provider"] == "aws":
        if len(f"AmazonEKSTFEBSCSIRole-{g['environment']}-{g['cluster_name']}-cluster") > 64:
            raise ValueError('global.cluster_name/environment: shorten names so the generated EBS CSI IAM role fits 64 characters')
        bucket = config['aws']['bucket_name']
        if ('..' in bucket or re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', bucket)
                or bucket.startswith(('xn--', 'sthree-', 'amzn-s3-demo-'))
                or bucket.endswith(('-s3alias', '--ol-s3', '.mrap', '--x-s3', '--table-s3'))):
            raise ValueError('aws.bucket_name: use a general-purpose S3 name without IP syntax or reserved prefixes/suffixes')
        vpc = network(config["network"]["vpc_cidr"], "network.vpc_cidr")
        if vpc.version != 4 or not 16 <= vpc.prefixlen <= 20:
            raise ValueError("network.vpc_cidr: use IPv4 with a prefix between /16 and /20")
        administrative_cidrs(config["eks"]["admin_cidrs"], "eks.admin_cidrs")
        scaling(config["eks"]["node_scaling"], "eks.node_scaling")
        if config["global"]["kubernetes_version"] != "1.35":
            raise ValueError("global.kubernetes_version: AWS requires 1.35 until the pinned autoscaler is upgraded")
    else:
        a = config["azure"]
        vnet = network(a["network"]["vnet_cidr"], "azure.network.vnet_cidr")
        subnet = network(a["network"]["subnet_cidr"], "azure.network.subnet_cidr")
        if vnet.version != 4 or subnet.version != 4 or not subnet.subnet_of(vnet):
            raise ValueError("azure.network.subnet_cidr: use an IPv4 subnet inside azure.network.vnet_cidr")
        if any(vnet.overlaps(ipaddress.ip_network(cidr)) for cidr in ('10.71.0.0/16', '10.72.0.0/16')):
            raise ValueError('azure.network.vnet_cidr: must not overlap the platform service/pod CIDRs 10.71.0.0/16 and 10.72.0.0/16')
        administrative_cidrs(a["network"]["api_server_authorized_ip_ranges"], "azure.network.api_server_authorized_ip_ranges")
        scaling(a["node_pool"], "azure.node_pool")


def validate_workload_identities(config):
    provider = config['global']['provider']
    subjects = set()
    for identity in config.get('workload_identities', {}).values():
        subject = (identity['namespace'], identity['service_account'])
        if subject in subjects:
            raise ValueError('workload_identities: each namespace/service_account pair must be unique')
        subjects.add(subject)
        if provider not in identity:
            raise ValueError('workload_identities: permissions for the active provider are required')
        if provider == 'azure':
            prefix = '/subscriptions/' + config['azure']['subscription_id'].lower() + '/'
            for assignment in identity['azure']['role_assignments']:
                if not all(assignment[field].lower().startswith(prefix) for field in ('scope', 'role_definition_id')):
                    raise ValueError('workload_identities.azure: scopes and roles must belong to the configured subscription')
                role = assignment['role_definition_id'].rsplit('/', 1)[-1].lower()
                if role in ('8e3af657-a8ff-443c-a75c-2fe8c4bcb635', 'b24988ac-6180-42a0-ab88-20f7382dd24c',
                            '18d7d88d-d35e-4fb5-a5c3-7773c20a72d9', 'f1a07417-d97a-45cb-824c-7a7467783830'):
                    raise ValueError('workload_identities.azure: broad administration roles are not supported')
        else:
            for statement in identity['aws']['statements']:
                if any(action.split(':')[0] in ('iam', 'organizations', 'account', 'sts') for action in statement['actions']):
                    raise ValueError('workload_identities.aws: identity or account administration and role chaining are not supported')
