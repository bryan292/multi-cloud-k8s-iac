#!/usr/bin/env python3
"""Run the selected cloud's isolated Terraform state bootstrap."""
import json
import subprocess
import sys
from pathlib import Path
try:
    from .config import load_config
    from .target import cloud_environment, check_identity, check_backend, check_bootstrap_state, pin_target, check_bootstrap_arguments
except ImportError:
    from config import load_config
    from target import cloud_environment, check_identity, check_backend, check_bootstrap_state, pin_target, check_bootstrap_arguments

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    check_bootstrap_arguments(arguments)
    c = load_config(ROOT / "config.yaml")
    provider = c["global"]["provider"]
    if provider == "aws":
        a = c["aws"]
        directory = ROOT / "bootstrap"
        values = {
            "account_id": a["account_id"], "region": a["state_region"],
            "bucket_name": a["bucket_name"],
        }
    elif provider == "azure":
        a, state = c["azure"], c["azure"]["state"]
        directory = ROOT / "bootstrap" / "azure"
        values = {
            "subscription_id": a["subscription_id"], "tenant_id": a["tenant_id"],
            "location": a["location"], "resource_group_name": state["resource_group_name"],
            "storage_account_name": state["storage_account_name"],
            "container_name": state["container_name"], "tags": c["global"]["common_tags"],
        }
    else:
        raise SystemExit(f"Unsupported provider: {provider}")
    env = cloud_environment(c)
    has_backend = check_bootstrap_state(c, directory)
    check_identity(c, env)
    if has_backend:
        check_backend(c, env)
    pin_target(c, ROOT, ["bootstrap"])
    env.update({f"TF_VAR_{key}": json.dumps(value) if isinstance(value, dict) else str(value) for key, value in values.items()})
    return subprocess.call(["terraform", f"-chdir={directory}", *arguments], env=env)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError:
        print("Bootstrap failed: check local file and executable access", file=sys.stderr)
        sys.exit(1)
