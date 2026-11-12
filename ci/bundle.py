#!/usr/bin/env python3
"""Encrypt exact plan bundles; reject unsafe archives and changed digests on restore."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crypt(source, target, decrypt=False):
    secret = os.environ.get('PLAN_ENCRYPTION_KEY', '')
    if len(secret) < 32 or '\n' in secret:
        raise ValueError('plan encryption requires a single-line secret of at least 32 characters')
    args = ['gpg', '--batch', '--yes', '--pinentry-mode', 'loopback', '--passphrase-fd', '0',
            '--output', str(target)]
    args += ['--decrypt', str(source)] if decrypt else ['--symmetric', '--cipher-algo', 'AES256', str(source)]
    result = subprocess.run(args, input=secret.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError('plan encryption/decryption failed')
    target.chmod(0o600)


def pack(events, destination):
    event = json.loads(Path(events).read_text().splitlines()[-1])
    run = Path(event['run_dir']).resolve()
    if event['event'] != 'run_completed' or event['status'] != 'planned':
        raise ValueError('planning did not complete')
    if run.parent != (Path.cwd() / '.iac/runs').resolve():
        raise ValueError('plan path is outside the run directory')
    if sha(run / 'manifest.json') != event['plan_digest']:
        raise ValueError('manifest changed after planning')
    target = Path(destination).resolve()
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / 'plan.tar'
        with tarfile.open(archive, 'w') as tar:
            for path in run.iterdir():
                if path.is_symlink() or not path.is_file():
                    raise ValueError('plan bundle must contain regular files only')
                tar.add(path, arcname=path.name)
        crypt(archive, target)
    return {'run_id': run.name, 'plan_digest': event['plan_digest'], 'bundle_digest': sha(target)}


def unpack(source, run_id, bundle_digest, plan_digest):
    if not run_id or Path(run_id).name != run_id or run_id in ('.', '..'):
        raise ValueError('invalid run identifier')
    if sha(source) != bundle_digest:
        raise ValueError('encrypted artifact digest mismatch')
    target = Path.cwd() / '.iac/runs' / run_id
    if target.exists():
        raise ValueError('refusing to overwrite a local run')
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / 'plan.tar'
        crypt(Path(source), archive, decrypt=True)
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            if not members or any(not m.isfile() or Path(m.name).name != m.name or m.name in ('.', '..') for m in members):
                raise ValueError('unsafe plan archive')
            if len({m.name for m in members}) != len(members):
                raise ValueError('duplicate archive paths')
            manifest = tar.extractfile('manifest.json').read()
            if hashlib.sha256(manifest).hexdigest() != plan_digest:
                raise ValueError('reviewed manifest digest mismatch')
            target.mkdir(parents=True, mode=0o700)
            for member in members:
                fd = os.open(target / member.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as out:
                    out.write(tar.extractfile(member).read())
    return target


if __name__ == '__main__':
    try:
        if sys.argv[1] == 'pack':
            values = pack(sys.argv[2], sys.argv[3])
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                for key, value in values.items():
                    stream.write(f'{key}={value}\n')
        elif sys.argv[1] == 'unpack':
            unpack(*sys.argv[2:])
        else:
            raise ValueError('invalid command')
    except (ValueError, OSError, KeyError, tarfile.TarError):
        print('plan bundle rejected; inspect private configuration and artifact integrity', file=sys.stderr)
        raise SystemExit(1)
