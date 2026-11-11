#!/usr/bin/env python3
"""Run Terraform for the state bucket. Review plan before applying its saved file."""
import json, os, subprocess, sys
from pathlib import Path
import yaml
root = Path(__file__).resolve().parents[1]
c = yaml.safe_load((root / "config.yaml").read_text())["global"]
env = dict(os.environ, TF_VAR_account_id=c["account_id"], TF_VAR_region=c["state_region"], TF_VAR_bucket_name=c["bucket_name"])
raise SystemExit(subprocess.call(["terraform", f"-chdir={root / 'bootstrap'}", *sys.argv[1:]], env=env))
