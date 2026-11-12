# Operational runbooks

## Failure during deployment

Read the failing stage's private `.iac/runs/<run-id>/*.log`; inspect actual cloud resources
before retrying. Use `deploy --resume RUN_DIR` with the original configuration and source.
Completed stages must remain free of drift; the interrupted stage gets a fresh plan.
If inputs changed, generate a new operation and review its plan. Do not remove remote state
or change backend coordinates to work around an error.

## Authentication and connectivity

Run `diagnose --offline` to check configuration and tools, then `diagnose` to check cloud
identity, backend and available cluster readiness. Check the selected profile/subscription,
trusted API CIDRs, VPN/private network route and the selected target kubeconfig. A missing
kubeconfig before cluster deployment is expected. Diagnostics are read-only and return a
nonzero status when checks are missing, fail or indicate resources are not ready.

## Flux and monitoring

With the selected `KUBECONFIG`, inspect `kubectl -n flux-system get
 gitrepositories,kustomizations,helmreleases` (on one line), then describe the failing object.
Check that the configured immutable commit is published and its provider/environment path
exists. Inspect events and controller logs privately. Use port-forward for monitoring;
retrieve credentials directly from Kubernetes Secrets without including values in tickets.
Alert delivery and SLO acceptance remain part of SPEC-008's future implementation.

## Upgrade and rollback

Back up state and application data first. Review Kubernetes/provider compatibility and
upgrade one supported Kubernetes minor at a time; review replacement and node-rollout plans.
Update locked providers deliberately, validate both clouds, deploy and verify. For a Flux
rollback, restore a known published umbrella commit in configuration and review/apply the
resulting plan. An application/chart rollback does not roll back a Kubernetes control plane;
managed control-plane downgrades are not an assumed recovery mechanism.

## Backup and restore scope

| Capability | AWS | Azure |
|---|---|---|
| Remote state protection | S3 versioning and encryption | Blob versioning and GRS |
| Storage smoke test | Encrypted gp3 persistence | Encrypted managed-csi persistence |
| Data restore acceptance | AWS Backup EBS restore smoke test | Not implemented |
| Scheduled application-aware backup | Requires separate configuration | Requires separate configuration |
| Full platform / regional recovery | Pending SPEC-006/007 | Pending SPEC-006/007 |

State versioning does not replace application backups. Do not declare a backup successful
until restoration has verified the data. `TEST_BACKUP=1 bash scripts/smoke-storage.sh` runs
the AWS-specific restore test; normal storage tests work on either provider. Smoke tests
remove their own temporary resources, so run them only when that cleanup is intended.

For suspected state corruption, stop concurrent operations, preserve the current state and
identify a known good backend version. Compare actual resources before restoring any state
version. This repository does not yet provide an automated or rehearsed full-state disaster
recovery workflow; never blindly overwrite a newer state snapshot.

## Retention and teardown

Failure and normal completion retain infrastructure. Cluster removal requires an explicit
`destroy` command and exact destination confirmation. State storage is retained even then.
Remove workload load balancers while controllers are alive; inspect orphaned disks, backups,
public IPs and DNS afterward. Follow [operations](operations.md#explicit-teardown). Do not use
teardown as an automatic final step of a deployment or validation workflow.
