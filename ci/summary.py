#!/usr/bin/env python3
"""Render only allowlisted plan counts and hashes in GitHub summaries."""
import json
import sys
from pathlib import Path

for line in Path(sys.argv[1]).read_text().splitlines():
    event = json.loads(line)
    if event.get('event') == 'planned':
        changes = event['changes']
        print(f"Stage `{event['stage']}`: " + ', '.join(f'{name}={int(changes[name])}' for name in ('create', 'update', 'delete', 'read')) + '\n')
    elif event.get('event') == 'run_completed':
        print(f"Reviewed manifest SHA256: `{event['plan_digest']}`\n")
