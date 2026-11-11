#!/usr/bin/env python3
"""Read-only AWS checks. No backend initialization or infrastructure creation."""
import argparse, ipaddress, json, subprocess, sys
from pathlib import Path
import yaml

def aws(*args):
    return json.loads(subprocess.check_output(["aws", *args, "--output", "json"], text=True))

def validate(config):
    g, n, e = config["global"], config["network"], config["eks"]
    if len(str(g["account_id"])) != 12 or not str(g["account_id"]).isdigit():
        raise ValueError("global.account_id must be a quoted 12-digit account ID")
    network = ipaddress.ip_network(n["vpc_cidr"])
    if network.version != 4 or not 16 <= network.prefixlen <= 20:
        raise ValueError("Use an IPv4 VPC CIDR between /16 and /20")
    for cidr in e["admin_cidrs"]:
        if ipaddress.ip_network(cidr).prefixlen == 0:
            raise ValueError("Public admin access cannot be unrestricted")
    scale = e["node_scaling"]
    if not 2 <= scale["min"] <= scale["desired"] <= scale["max"]:
        raise ValueError("Require 2 <= min <= desired <= max")
    if config["umbrella"]["cluster_autoscaler"] and g["kubernetes_version"] != "1.35":
        raise ValueError("Update the pinned autoscaler chart/image together with Kubernetes (currently 1.35)")
    if not e["admin_principal_arns"]:
        raise ValueError("At least one EKS administrator is required")
    return config

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    c = validate(yaml.safe_load(Path(args.config).read_text()))
    if args.offline:
        print("Configuration checks passed")
        return
    g = c["global"]
    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != g["account_id"]:
        raise ValueError("Active AWS account does not match configuration")
    if identity["Arn"].endswith(":root"):
        raise ValueError("Select an IAM user/role profile; root credentials are not supported for deployment")
    arn = identity["Arn"]
    if ":assumed-role/" in arn:
        role_name = arn.split(":assumed-role/", 1)[1].split("/")[0]
        arn = aws("iam", "get-role", "--role-name", role_name)["Role"]["Arn"]
    if arn not in c["eks"]["admin_principal_arns"]:
        raise ValueError("Deployment identity must be listed in eks.admin_principal_arns")
    print("Identity:", arn)
    addons = aws("eks", "describe-addon-versions", "--region", g["region"], "--kubernetes-version", g["kubernetes_version"])
    names = {"coredns":"coredns", "kube-proxy":"kube_proxy", "vpc-cni":"vpc_cni", "aws-ebs-csi-driver":"ebs_csi"}
    for name, key in names.items():
        versions = next((a["addonVersions"] for a in addons["addons"] if a["addonName"] == name), [])
        if not versions:
            raise ValueError(f"No compatible {name} for Kubernetes {g['kubernetes_version']}")
        pin = c["eks"]["addon_versions"].get(key)
        if pin and pin not in [v["addonVersion"] for v in versions]:
            raise ValueError(f"Unsupported {name} version: {pin}")
        print(f"{key}: {pin or versions[0]['addonVersion']}")
    if c["umbrella"]["external_dns"] or c["umbrella"]["cert_manager"]:
        zone = aws("route53", "get-hosted-zone", "--id", c["network"]["hosted_zone_id"])["HostedZone"]
        domain = c["network"]["domain"].rstrip('.')
        zone_name = zone["Name"].rstrip('.')
        if zone["Config"]["PrivateZone"] or not (domain == zone_name or domain.endswith('.'+zone_name)):
            raise ValueError("DNS domain must belong to the configured public hosted zone")
    print("AWS preflight passed; review a saved plan before applying")
if __name__ == "__main__":
    try: main()
    except (ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        sys.exit(1)
