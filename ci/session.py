#!/usr/bin/env python3
"""Prepare private config and ephemeral AWS profile after an OIDC login action."""
import configparser
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.config import load_config


def prepare(directory):
    root = Path(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    config = root / 'config.json'
    fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(os.environ['IAC_CONFIG_JSON'])
    value = load_config(config)
    if value['global']['provider'] != os.environ['IAC_PROVIDER'] or value['global']['environment'] != os.environ['IAC_ENVIRONMENT']:
        raise ValueError('environment configuration does not match requested destination')
    if value['global']['provider'] == 'aws':
        credentials = configparser.RawConfigParser()
        credentials[value['aws']['profile']] = {
            'aws_access_key_id': os.environ['AWS_ACCESS_KEY_ID'],
            'aws_secret_access_key': os.environ['AWS_SECRET_ACCESS_KEY'],
            'aws_session_token': os.environ['AWS_SESSION_TOKEN'],
        }
        path = root / 'aws-credentials'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            credentials.write(stream)
        with open(os.environ['GITHUB_ENV'], 'a') as stream:
            stream.write(f'AWS_SHARED_CREDENTIALS_FILE={path.resolve()}\n')
    return config


if __name__ == '__main__':
    try:
        prepare(sys.argv[1])
    except (ValueError, KeyError, OSError):
        print('OIDC session preparation failed; check private configuration and temporary credentials', file=sys.stderr)
        raise SystemExit(1)
