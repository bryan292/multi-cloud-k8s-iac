#!/usr/bin/env python3
"""Run the same staged Terragrunt workflow for AWS or Azure."""
import argparse
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def run(stage, *arguments):
    directory = ROOT / "deployment-config" / stage
    print(f"\n==> {stage}: terragrunt {' '.join(arguments)}", flush=True)
    subprocess.run(["terragrunt", *arguments], cwd=directory, check=True)


def stages(provider):
    cloud = ["aws/network", "aws/eks"] if provider == "aws" else ["azure/aks"]
    return [*cloud, "kubernetes", "kube_resources"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "deploy", "destroy", "verify"))
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    provider = config["global"]["provider"]
    if provider not in {"aws", "azure"}:
        raise SystemExit("global.provider must be aws or azure")

    if args.action == "verify":
        subprocess.run([sys.executable, ROOT / "scripts" / "verify-cluster.py"], check=True)
        return

    selected = stages(provider)
    if args.action == "destroy":
        for stage in reversed(selected):
            run(stage, "plan", "-destroy", "-out=destroy.tfplan")
            run(stage, "apply", "destroy.tfplan")
        return

    for stage in selected:
        run(stage, "plan", "-out=deploy.tfplan")
        if args.action == "deploy":
            run(stage, "apply", "deploy.tfplan")


if __name__ == "__main__":
    main()
