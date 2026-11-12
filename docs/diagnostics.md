# Read-only diagnostics

Use the same command for EKS and AKS:

```sh
python3 scripts/iac.py --config config.yaml diagnose
python3 scripts/iac.py --config config.yaml --json diagnose
python3 scripts/iac.py --config config.yaml --json diagnose --offline
```

Offline mode validates configuration and installed tools without cloud or Kubernetes calls.
Online mode checks the configured cloud identity before the backend and cluster. An identity
mismatch prevents subsequent requests. The selected target's kubeconfig is used; the managed
`cluster-settings` ConfigMap must match the expected provider and cluster name before resource
inventory continues. Backend failure remains visible while Kubernetes investigation can
continue with a verified identity. A local lock prevents overlap with another operation for
the destination.

| Check | What it establishes |
|---|---|
| API/nodes | Authenticated API access, Ready nodes and configured minimum count |
| Flux | Nonempty sources/reconcilers/releases, Ready conditions and current observed generations |
| Metrics | CPU/memory samples cover all known nodes |
| CSI | Provider disk driver registered globally and on every known node |
| DNS | CoreDNS deployment availability and ready kube-dns EndpointSlice addresses |
| Certificates/issuers | Ready conditions of configured cert-manager resources |
| Ingress | Resource count and whether addresses have been reported |
| Quotas | Kubernetes ResourceQuota usage compared with limits using normalized quantities |

These are state checks. They do not establish successful DNS resolution from an application,
volume provisioning, HTTP reachability, certificate validation at an endpoint, or cloud
service-quota/billing headroom. Use the dedicated smoke and observability checks where needed.
Optional certificates, issuers, ingress or quotas with no resources report `not_configured`;
a forbidden API or timeout reports failure, never absence. Missing CSI or metrics coverage
and stale Flux generations fail. Ingress addresses pending and quota limits at capacity are
warnings, including deliberately configured zero limits.

Each NDJSON result has `event: diagnostic`, a stable `check` name, `status`, bounded counts
and a recovery `hint` when appropriate. `diagnostic_summary` includes failed/warning counts.
Exit code is 1 if a required check fails, 0 otherwise; warnings remain visible with exit 0.
The human format carries the same fields. No raw stderr, object manifests, Secret data,
logs, kubeconfig or credentials are included. Kubernetes commands are exclusively `get`,
with a 30-second timeout per request. Cloud identity/backend reads use their existing
90-second timeout. No auto-repair or active workload probe is performed.

For a failure, first check the reported destination and hint. Restore credentials or network
access before rerunning. Do not change an unrelated resource to make a diagnostic green.
Further operational procedures are in [runbooks](runbooks.md).

References: [Kubernetes service debugging](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/)
and [resource quota semantics](https://kubernetes.io/docs/concepts/policy/resource-quotas/).
