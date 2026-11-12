#!/usr/bin/env python3
"""Migrate historical YAML to v1 without changing resource names or backend keys."""
import argparse
import copy
import os
import sys
import tempfile
from pathlib import Path

import yaml
from config import validate, parse_yaml


def migrate(value):
    if not isinstance(value, dict):
        raise ValueError("config: expected a YAML mapping")
    result = copy.deepcopy(value)
    if 'schema_version' not in result:
        # Match the historical Terraform optional attributes exactly.
        result.setdefault('application', {})
        if isinstance(result['application'], dict):
            for key, default in {'enabled': False, 'repository': '', 'commit': '', 'path': './', 'secret_name': ''}.items():
                result['application'].setdefault(key, default)
        if isinstance(result.get('platform'), dict):
            result['platform'].setdefault('secret_name', '')
    result.setdefault("schema_version", 1)
    return validate(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--in-place", action="store_true", help="Write source after creating an exclusive .bak backup")
    args = parser.parse_args()
    original = args.source.read_bytes()
    try:
        result = migrate(parse_yaml(original))
    except (yaml.YAMLError, UnicodeError):
        raise ValueError("config: expected valid YAML; check syntax") from None
    output = yaml.safe_dump(result, sort_keys=False)
    if args.in_place:
        if original == output.encode():
            return
        backup = args.source.with_name(args.source.name + ".bak")
        with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
            stream.write(original)
        # Replace atomically so an interrupted write cannot truncate the source.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=args.source.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(output)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(args.source)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError:
        print("Migration failed: check source access and whether a .bak backup already exists", file=sys.stderr)
        sys.exit(1)
