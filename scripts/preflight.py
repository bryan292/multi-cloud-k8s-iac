#!/usr/bin/env python3
"""Read-only configuration and cloud identity checks for AWS or Azure."""
import argparse
import ipaddress
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

import yaml


def command_json(*args):
    return json.loads(subprocess.check_output(args, text=True))


def validate(config):
    g = config["global"]
    provider = g.get("provider")
    if provider not in {"aws", "azure"}:
        raise ValueError("global.provider must be aws or azure")
    if not re.fullmatch(r"1\.\d{2}", str(g["kubernetes_version"])):
        raise ValueError("global.kubernetes_version must be a Kubernetes minor such as 1.35")
    platform = config["platform"]
    if not re.fullmatch(r"[0-9a-f]{40}", str(platform["commit"])):
        raise ValueError("platform.commit must be a published 40-character Git commit")
    if not str(platform["repository"]).startswith("https://"):
        raise ValueError("platform.repository must use HTTPS")

    if provider == "aws":
        a, n, e = config["aws"], config["network"], config["eks"]
        if len(str(a["account_id"])) != 12 or not str(a["account_id"]).isdigit():
            raise ValueError("aws.account_id must be a quoted 12-digit account ID")
        network = ipaddress.ip_network(n["vpc_cidr"])
        if network.version != 4 or not 16 <= network.prefixlen <= 20:
            raise ValueError("Use an IPv4 VPC CIDR between /16 and /20")
        for cidr in e["admin_cidrs"]:
            if ipaddress.ip_network(cidr).prefixlen == 0:
                raise ValueError("Public admin access cannot be unrestricted")
        scale = e["node_scaling"]
        if not 2 <= scale["min"] <= scale["desired"] <= scale["max"]:
            raise ValueError("Require 2 <= min <= desired <= max")
        if g["kubernetes_version"] != "1.35":
            raise ValueError("Update the pinned autoscaler chart/image together with Kubernetes (currently 1.35)")
        if not e["admin_principal_arns"]:
            raise ValueError("At least one EKS administrator is required")
    else:
        a = config["azure"]
        for field in ("subscription_id", "tenant_id"):
            try:
                uuid.UUID(str(a[field]))
            except (ValueError, AttributeError):
                raise ValueError(f"azure.{field} must be a UUID") from None
        account = a["state"]["storage_account_name"]
        if not re.fullmatch(r"[a-z0-9]{3,24}", account):
            raise ValueError("Azure state storage account names require 3-24 lowercase letters or digits")
        vnet = ipaddress.ip_network(a["network"]["vnet_cidr"])
        subnet = ipaddress.ip_network(a["network"]["subnet_cidr"])
        if vnet.version != 4 or subnet.version != 4 or not subnet.subnet_of(vnet):
            raise ValueError("The Azure subnet must be an IPv4 subnet inside the configured VNet")
        for cidr in a["network"]["api_server_authorized_ip_ranges"]:
            if ipaddress.ip_network(cidr).prefixlen == 0:
                raise ValueError("AKS API access cannot be unrestricted")
        scale = a["node_pool"]
        if not 2 <= scale["min"] <= scale["desired"] <= scale["max"]:
            raise ValueError("Require 2 <= min <= desired <= max")
    return config


def aws_preflight(config):
    g, a = config["global"], config["aws"]
    base = ["aws", "--profile", a["profile"]]
    identity = command_json(*base, "sts", "get-caller-identity", "--output", "json")
    if identity["Account"] != a["account_id"]:
        raise ValueError("Active AWS account does not match configuration")
    if identity["Arn"].endswith(":root"):
        raise ValueError("Select an IAM user/role profile; root credentials are not supported")
    arn = identity["Arn"]
    if ":assumed-role/" in arn:
        role_name = arn.split(":assumed-role/", 1)[1].split("/")[0]
        arn = command_json(*base, "iam", "get-role", "--role-name", role_name, "--output", "json")["Role"]["Arn"]
    if arn not in config["eks"]["admin_principal_arns"]:
        raise ValueError("Deployment identity must be listed in eks.admin_principal_arns")
    print("Identity:", arn)
    addons = command_json(*base, "eks", "describe-addon-versions", "--region", a["region"], "--kubernetes-version", g["kubernetes_version"], "--output", "json")
    names = {"coredns": "coredns", "kube-proxy": "kube_proxy", "vpc-cni": "vpc_cni", "aws-ebs-csi-driver": "ebs_csi"}
    for name, key in names.items():
        versions = next((item["addonVersions"] for item in addons["addons"] if item["addonName"] == name), [])
        pin = config["eks"]["addon_versions"].get(key)
        if not versions or (pin and pin not in [item["addonVersion"] for item in versions]):
            raise ValueError(f"Unsupported {name} version: {pin}")
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
    account = command_json("az", "account", "show", "--output", "json")
    if account["id"] != a["subscription_id"] or account["tenantId"] != a["tenant_id"]:
        raise ValueError("Active Azure subscription or tenant does not match configuration")
    versions = set(find_versions(command_json("az", "aks", "get-versions", "--location", a["location"], "--output", "json")))
    if g["kubernetes_version"] not in versions:
        raise ValueError(f"AKS {g['kubernetes_version']} is not available in {a['location']}")
    provider = command_json("az", "provider", "show", "--namespace", "Microsoft.ContainerService", "--output", "json")
    if provider["registrationState"] != "Registered":
        raise ValueError("Microsoft.ContainerService is not registered in the subscription")
    print("Identity:", account["user"]["name"])
    print("AKS version:", g["kubernetes_version"])
    print("Azure preflight passed; review a saved plan before applying")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    config = validate(yaml.safe_load(Path(args.config).read_text()))
    if args.offline:
        print("Configuration checks passed")
        return
    (aws_preflight if config["global"]["provider"] == "aws" else azure_preflight)(config)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        sys.exit(1)
