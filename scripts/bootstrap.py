#!/usr/bin/env python3
"""Run the selected cloud's isolated Terraform state bootstrap."""
import json, os, subprocess, sys
from pathlib import Path
import yaml
root = Path(__file__).resolve().parents[1]
c = yaml.safe_load((root / "config.yaml").read_text())
provider = c["global"]["provider"]
if provider == "aws":
    a = c["aws"]
    directory = root / "bootstrap"
    values = {
        "account_id": a["account_id"], "region": a["state_region"],
        "bucket_name": a["bucket_name"],
    }
elif provider == "azure":
    a, state = c["azure"], c["azure"]["state"]
    directory = root / "bootstrap" / "azure"
    values = {
        "subscription_id": a["subscription_id"], "tenant_id": a["tenant_id"],
        "location": a["location"], "resource_group_name": state["resource_group_name"],
        "storage_account_name": state["storage_account_name"],
        "container_name": state["container_name"], "tags": c["global"]["common_tags"],
    }
else:
    raise SystemExit(f"Unsupported provider: {provider}")
env = dict(os.environ, **{f"TF_VAR_{key}": json.dumps(value) if isinstance(value, dict) else str(value) for key, value in values.items()})
raise SystemExit(subprocess.call(["terraform", f"-chdir={directory}", *sys.argv[1:]], env=env))
