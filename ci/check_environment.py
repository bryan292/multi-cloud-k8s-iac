#!/usr/bin/env python3
"""Fail closed unless the apply environment has an repository-owner approval gate."""
import json
import os
import subprocess
import sys
from urllib.parse import quote


def enforce(environment, branch, owner):
    rules = environment.get('protection_rules', [])
    reviewers = [rule for rule in rules if rule.get('type') == 'required_reviewers']
    if len(reviewers) != 1 or owner.get('type') != 'User' or not isinstance(owner.get('id'), int):
        raise ValueError('apply environment requires the personal repository owner as sole reviewer')
    allowed = reviewers[0].get('reviewers', [])
    if (len(allowed) != 1 or allowed[0].get('type') != 'User' or
            allowed[0].get('reviewer', {}).get('id') != owner['id']):
        raise ValueError('apply environment must list only the repository owner as reviewer')
    if reviewers[0].get('prevent_self_review') is not False:
        raise ValueError('owner-only approval must allow the owner to approve their own dispatch')
    policy = environment.get('deployment_branch_policy') or {}
    if not policy.get('protected_branches') or not branch.get('protected'):
        raise ValueError('apply environment must allow only protected branches, including the default branch')


def get(path):
    result = subprocess.run(['gh', 'api', path], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


if __name__ == '__main__':
    try:
        repo = os.environ['GITHUB_REPOSITORY']
        environment = quote(os.environ['APPLY_ENVIRONMENT'], safe='')
        branch = quote(os.environ['DEFAULT_BRANCH'], safe='')
        enforce(get(f'repos/{repo}/environments/{environment}'), get(f'repos/{repo}/branches/{branch}'),
                get(f'repos/{repo}')['owner'])
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError)
              else 'cannot verify apply environment approval and branch protection', file=sys.stderr)
        raise SystemExit(1)
