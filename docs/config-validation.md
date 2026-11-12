# Configuration v1 acceptance — 2026-11-11

SPEC-001 is implemented and verified offline and on live AWS/Azure infrastructure.
Temporary deployment, testing and teardown were explicitly authorized. Backends
were retained; no commit or push was performed.

## Implementation

- JSON Schema v1, shared offline validation, provider-specific examples and safe
  migration with an exclusive 0600 backup and atomic source replacement.
- Identity/backend checks before operational plans; authenticated child-process
  environments, existing state/cache checks and local destination pins.
- Sanitized errors, duplicate-key rejection, immutable Git sources, provider naming,
  administrative CIDR and scaling validation.
- Pinned Python dependencies installed in the CI container; Azure provider checksums
  repaired for Darwin ARM64, Linux ARM64 and Linux AMD64 without version upgrades.
- Smoke tests updated to the v1 contract. Storage supports both CSI implementations
  and explicitly fails for corrupt data or absent encryption, including on macOS Bash.

## Automated checks

| Check | Result |
|---|---|
| Python suite on macOS, Linux ARM64 and Linux AMD64 | 41 passed on each |
| Terraform mock tests on all three platforms | 9 passed on each |
| Terraform/Terragrunt formatting and module validation | Passed |
| Offline Terragrunt renders | Seven AWS/Azure stages passed; backend keys unchanged |
| Linux ARM64 and AMD64 container builds | Passed |
| Migration and backup | Repeatable; original preserved by default; explicit local migration verified |
| Git whitespace validation | Passed |

## Live acceptance

| Check | AWS | Azure |
|---|---|---|
| Identity and backend validation | Passed | Passed |
| Deployment | Network, EKS, Flux, platform | AKS, Flux, platform |
| Nodes and metrics | Two Ready nodes; metrics available | Two Ready nodes; metrics available |
| Platform reconciliation | Six HelmReleases Ready; four add-ons ACTIVE/healthy | Cert-manager and monitoring Ready |
| Storage | Encrypted gp3; data survived pod recreation | Encrypted managed-csi; data survived pod recreation |
| Recovery | AWS Backup recovery point restored to a new EBS volume; data verified | Outside SPEC-001 backup scope |
| Network and certificates | ALB HTTP, Route53 alias and self-signed certificate | LoadBalancer HTTP and self-signed certificate |
| Final deployment plans | Four exit-0 plans, no changes | Three exit-0 plans, no changes |
| Final bootstrap plan | Exit 0, no changes | Exit 0, no changes |

External HTTP access was restricted to the current administrator /32 in isolated
configuration copies. Initial ALB DNS propagation delayed the HTTP check; target
health and resolver checks confirmed the endpoint and the test subsequently passed.
No public ACME issuance or application-specific database recovery is claimed.

## Cleanup

All temporary application namespaces, test load balancers/DNS records, backup
recovery points and restored/test volumes were removed. Platform PVCs and retained
EBS volumes were explicitly cleaned before removing nodes and controllers.

Azure cluster and node resource groups are absent; all three deployment state blobs
contain zero resources and outputs. AWS deployment states are empty; EKS/VPC are
removed, instances terminated, NAT gateways deleted, and associated interfaces,
volumes, load balancers/target groups, backup vault and Elastic IPs are absent. The temporary EKS
KMS key is in PendingDeletion, scheduled for December 11, 2026 (America/Costa_Rica),
under AWS's deletion window; it is not an active cluster resource. Backend storage remains reachable in both providers.

The final private cleanup log records the KMS deletion deadline and resource checks.
Local configurations, backups, pins, kubeconfigs, plans and `.sdd` are excluded from
Git/build context. Kubeconfigs for the removed temporary clusters were deleted.

## Reproduction

```sh
scripts/validate.sh
uv run --with-requirements requirements.txt python -m unittest discover -s tests -p 'test_*.py'
docker build -t multi-cloud-k8s-iac:validate .
# Use a clean checkout without local state/credentials or host .terraform caches.
docker run --rm -v "$PWD:/app" multi-cloud-k8s-iac:validate scripts/validate.sh
```

The local CI command passed; no remote GitHub Actions run was triggered. Live test
commands and provider restrictions are documented in the repository README.
