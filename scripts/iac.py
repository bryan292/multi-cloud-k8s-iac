#!/usr/bin/env python3
"""Unified multi-cloud operations; destructive actions always require confirmation."""
import argparse
import json
import sys

import yaml
from pathlib import Path

try:
    from .diagnostics import diagnose
    from .workload_identity import export as export_identities
    from .operations import Operations
except ImportError:
    from diagnostics import diagnose
    from workload_identity import export as export_identities
    from operations import Operations

ROOT = Path(__file__).resolve().parents[1]


class CLIParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('invalid command arguments; use --help for the command syntax')


def parser():
    result = CLIParser(description=__doc__)
    result.add_argument('--config', type=Path, default=ROOT / 'config.yaml')
    result.add_argument('--json', action='store_true', help='Emit NDJSON events without raw tool output')
    sub = result.add_subparsers(dest='command', required=True)
    for name in ('plan', 'deploy', 'destroy', 'bootstrap'):
        item = sub.add_parser(name)
        if name != 'bootstrap':
            item.add_argument('--stage', action='append', help='Select a stage; may be repeated')
        if name != 'plan':
            item.add_argument('--plan-only', action='store_true')
            item.add_argument('--plan-dir', type=Path)
            item.add_argument('--plan-digest')
            item.add_argument('--resume', type=Path)
        if name == 'destroy':
            item.add_argument('--confirm-destroy', required=True, metavar='PROVIDER/ENVIRONMENT/CLUSTER')
    identities = sub.add_parser('identities', help='Export deployed ServiceAccounts for GitOps (read-only)')
    identities.add_argument('--format', choices=('yaml', 'json'), default='yaml')
    sub.add_parser('verify')
    diagnose = sub.add_parser('diagnose')
    diagnose.add_argument('--offline', action='store_true')
    return result


def emitter(structured):
    def emit(**event):
        if structured:
            print(json.dumps(event, sort_keys=True), flush=True)
        else:
            print(' '.join(f'{key}={value}' for key, value in event.items()), flush=True)
    return emit


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    emit = emitter('--json' in arguments)
    try:
        args = parser().parse_args(arguments)
        operation = Operations(ROOT, args.config, emit)
        if args.command == 'identities':
            with operation.lock():
                values = export_identities(operation.config)
            if args.format == 'json' or args.json:
                print(json.dumps(values, sort_keys=True))
            else:
                print(yaml.safe_dump_all([item['service_account'] for item in values.values()], sort_keys=False), end='')
            return 0
        if args.command == 'diagnose':
            with operation.lock():
                return diagnose(operation, emit, args.offline)
        if args.command == 'verify':
            with operation.lock():
                operation.start('verify', [])
                try:
                    operation.prepare()
                    operation.runner.run([sys.executable, str(ROOT / 'scripts/verify-cluster.py')], ROOT,
                                         operation.env, operation.run_dir / 'verify.log')
                    operation.manifest['status'] = 'completed'
                    operation.save()
                except (Exception, KeyboardInterrupt):
                    operation.manifest['status'] = 'failed'
                    operation.save()
                    raise
                emit(event='verified', provider=operation.provider, run_dir=str(operation.run_dir))
            return 0
        operation.execute('deploy' if args.command == 'plan' else args.command,
                          requested=getattr(args, 'stage', None),
                          plan_only=args.command == 'plan' or getattr(args, 'plan_only', False),
                          plan_dir=getattr(args, 'plan_dir', None), plan_digest=getattr(args, 'plan_digest', None),
                          resume=getattr(args, 'resume', None), confirm=getattr(args, 'confirm_destroy', None))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        # ValueError messages are controlled by our validators/runner; never echo OS paths/CLI output.
        message = str(exc) if isinstance(exc, ValueError) else 'operation failed; check configuration, files and private logs'
        emit(event='error', message=message)
        return 1
    except KeyboardInterrupt:
        emit(event='interrupted', message='operation interrupted; inspect state and resume the recorded run')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
