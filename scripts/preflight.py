#!/usr/bin/env python3
"""Read-only configuration and cloud identity checks for AWS or Azure."""
import argparse
from functools import partial
import subprocess
import sys

try:
    from .config import load_config, validate
    from .target import command_json, cloud_environment, check_identity, check_backend
except ImportError:
    from config import load_config, validate
    from target import command_json, cloud_environment, check_identity, check_backend


def aws_preflight(config):
    g, a = config["global"], config["aws"]
    base = ["aws", "--profile", a["profile"]]
    env = cloud_environment(config)
    identity = check_identity(config, env)
    check_backend(config, env)
    query = partial(command_json, env=env)
    arn = identity["Arn"]
    if ":assumed-role/" in arn:
        role_name = arn.split(":assumed-role/", 1)[1].split("/")[0]
        arn = query(*base, "iam", "get-role", "--role-name", role_name, "--output", "json")["Role"]["Arn"]
    if arn not in config["eks"]["admin_principal_arns"]:
        raise ValueError("Deployment identity must be listed in eks.admin_principal_arns")
    addons = query(*base, "eks", "describe-addon-versions", "--region", a["region"], "--kubernetes-version", g["kubernetes_version"], "--output", "json")
    names = {"coredns": "coredns", "kube-proxy": "kube_proxy", "vpc-cni": "vpc_cni", "aws-ebs-csi-driver": "ebs_csi"}
    for name, key in names.items():
        versions = next((item["addonVersions"] for item in addons["addons"] if item["addonName"] == name), [])
        pin = config["eks"]["addon_versions"].get(key)
        if not versions or (pin and pin not in [item["addonVersion"] for item in versions]):
            raise ValueError(f"eks.addon_versions.{key}: select a version compatible with the configured Kubernetes minor")
        print(f"{key}: {pin or versions[0]['addonVersion']}")
    print("AWS preflight passed; review a saved plan before applying")


def find_versions(value):
    if isinstance(value, dict):
        if isinstance(value.get("version"), str):
            yield value["version"]
        for item in value.values():
            yield from find_versions(item)
    elif isinstance(value, list):
        for item in value:
            yield from find_versions(item)


def azure_preflight(config):
    g, a = config["global"], config["azure"]
    env = cloud_environment(config)
    check_identity(config, env)
    check_backend(config, env)
    query = partial(command_json, env=env)
    versions = set(find_versions(query("az", "aks", "get-versions", "--location", a["location"], "--output", "json")))
    if g["kubernetes_version"] not in versions:
        raise ValueError("global.kubernetes_version: select an AKS version available in azure.location")
    provider = query("az", "provider", "show", "--namespace", "Microsoft.ContainerService", "--output", "json")
    if provider["registrationState"] != "Registered":
        raise ValueError("Microsoft.ContainerService is not registered in the subscription")
    print("AKS version:", g["kubernetes_version"])
    print("Azure preflight passed; review a saved plan before applying")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.offline:
        print("Configuration checks passed")
        return
    (aws_preflight if config["global"]["provider"] == "aws" else azure_preflight)(config)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        sys.exit(1)
