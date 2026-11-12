#!/usr/bin/env python3
"""Read-only post-apply checks shared by EKS and AKS."""
import json
import os
import subprocess
import time
from pathlib import Path

from config import load_config

root = Path(__file__).resolve().parents[1]
config = load_config(os.environ.get("IAC_CONFIG", root / "config.yaml"))
provider = config["global"]["provider"]
os.environ.setdefault("KUBECONFIG", str(root / "kubeconfig.yaml"))


def kube(*args):
    return subprocess.check_output(["kubectl", *args], text=True)


nodes = json.loads(kube("get", "nodes", "-o", "json"))["items"]
minimum = config["eks"]["node_scaling"]["min"] if provider == "aws" else config["azure"]["node_pool"]["min"]
assert len(nodes) >= minimum, "Missing nodes"
assert all(any(item["type"] == "Ready" and item["status"] == "True" for item in node["status"]["conditions"]) for node in nodes), "Unready nodes"

cluster = f"{config['global']['environment']}-{config['global']['cluster_name']}-cluster"
if provider == "aws":
    for addon in ["coredns", "kube-proxy", "vpc-cni", "aws-ebs-csi-driver"]:
        result = json.loads(subprocess.check_output([
            "aws", "--profile", config["aws"]["profile"], "eks", "describe-addon",
            "--cluster-name", cluster, "--addon-name", addon, "--region", config["aws"]["region"], "--output", "json",
        ], text=True))["addon"]
        assert result["status"] == "ACTIVE" and not result["health"]["issues"], result
        print("PASS EKS addon", addon, flush=True)
else:
    result = json.loads(subprocess.check_output([
        "az", "aks", "show", "--subscription", config["azure"]["subscription_id"],
        "--resource-group", config["azure"]["resource_group_name"], "--name", cluster, "--output", "json",
    ], text=True))
    assert result["provisioningState"] == "Succeeded" and result["powerState"]["code"] == "Running", result
    print("PASS AKS control plane", flush=True)

expected = {"cert-manager", "monitoring"}
if provider == "aws":
    expected |= {"metrics-server", "aws-load-balancer-controller", "cluster-autoscaler", "external-dns"}
deadline = time.monotonic() + 1200
while True:
    releases = json.loads(kube("get", "helmreleases", "-n", "flux-system", "-o", "json"))["items"]
    ready = {
        release["metadata"]["name"] for release in releases
        if any(condition["type"] == "Ready" and condition["status"] == "True" and condition.get("observedGeneration") == release["metadata"]["generation"] for condition in release.get("status", {}).get("conditions", []))
    }
    if expected <= ready:
        break
    if time.monotonic() >= deadline:
        raise SystemExit(f"Flux reconciliation timed out: {expected - ready}")
    print("Waiting for Flux:", sorted(expected - ready), flush=True)
    time.sleep(15)
print("PASS HelmReleases:", ", ".join(sorted(ready)), flush=True)
print(kube("top", "nodes"))
print("Cluster verification passed")
