#!/usr/bin/env python3
"""Read-only checks after apply; use the root kubeconfig and deployment AWS profile."""
import json, os, subprocess, time
from pathlib import Path
import yaml
root = Path(__file__).resolve().parents[1]
c = yaml.safe_load((root / "config.yaml").read_text())
os.environ.setdefault("KUBECONFIG", str(root / "kubeconfig.yaml"))
def kube(*args):
    return subprocess.check_output(["kubectl", *args], text=True)
cluster = f"{c['global']['environment']}-{c['global']['cluster_name']}-cluster"
nodes = json.loads(kube("get", "nodes", "-o", "json"))["items"]
assert len(nodes) >= c["eks"]["node_scaling"]["min"], "Missing nodes"
assert all(any(s["type"] == "Ready" and s["status"] == "True" for s in n["status"]["conditions"]) for n in nodes), "Unready nodes"
for addon in ["coredns", "kube-proxy", "vpc-cni", "aws-ebs-csi-driver"]:
    result = json.loads(subprocess.check_output(["aws", "eks", "describe-addon", "--cluster-name", cluster, "--addon-name", addon, "--region", c["global"]["region"], "--output", "json"], text=True))["addon"]
    assert result["status"] == "ACTIVE" and not result["health"]["issues"], result
    print("PASS EKS addon", addon, flush=True)
expected = {name.replace('_','-') for name, enabled in c["umbrella"].items() if enabled}
deadline = time.monotonic() + 900
while True:
    releases = json.loads(kube("get", "helmreleases", "-n", "flux-system", "-o", "json"))["items"]
    ready = {r["metadata"]["name"] for r in releases if any(x["type"] == "Ready" and x["status"] == "True" and x.get("observedGeneration") == r["metadata"]["generation"] for x in r.get("status",{}).get("conditions",[]))}
    if expected <= ready: break
    if time.monotonic() >= deadline: raise SystemExit(f"Flux reconciliation timed out: {expected-ready}")
    print("Waiting for Flux:", sorted(expected-ready), flush=True)
    time.sleep(15)
print("PASS HelmReleases:", ', '.join(sorted(ready)), flush=True)
if c["umbrella"]["metrics_server"]:
    print(kube("top", "nodes"))
print("Cluster verification passed")
