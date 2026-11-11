# AWS validation — 2026-11-10

The updated stack was deployed to `us-east-1` as `dev-iac-test-cluster`, using the personal-account IAM profile selected by the owner. The owner requested that the cluster remain deployed. No Git push was performed.

## Verified

| Check | Result |
|---|---|
| Terraform formatting and validation | Bootstrap and all four deployment modules passed |
| Terraform mocked plans | 7 tests passed: network CIDR/AZs, EKS access/scaling, webhook ordering and optional dependencies |
| Python tests | 7 tests passed: configuration rejection paths and exact DNS ownership-record cleanup |
| Container builds | Linux ARM64 and AMD64 built; pinned tool binaries executed successfully |
| Provider reproducibility | Lock files include Darwin ARM64, Linux ARM64 and Linux AMD64 checksums |
| Helm rendering | All eight pinned charts rendered, including optional Loki and Flux CRDs |
| AWS prerequisites | Account identity, actual public IP, hosted zone and Kubernetes/add-on compatibility verified |
| EKS | Kubernetes 1.35; two ready private AL2023 managed nodes; four active EKS add-ons |
| Access | IAM user access worked; public API restricted to the owner's supplied `/32`; private API enabled |
| Flux | Six enabled HelmReleases reconciled at their current generation |
| Metrics | `kubectl top nodes` returned CPU and memory data |
| Storage | Encrypted gp3 PVC bound; written data survived pod deletion/recreation |
| Backup | AWS Backup completed a recovery point; a new volume restored from its snapshot contained the original data |
| Networking | An ALB served HTTP from a test pod, restricted to the configured client CIDR |
| DNS | ExternalDNS created Route53 alias records under the configured subdomain |
| Certificates | cert-manager issued a self-signed test certificate |
| Idempotency | Final plans for network, EKS, Flux and platform resources reported no changes |
| Cleanup | Test namespace, ALB, alias/TXT records, original/restored test volumes and test recovery point removed |

The three remaining application EBS volumes belong to monitoring (Prometheus, Alertmanager and Grafana), are encrypted, and are tagged for the daily backup plan. The state bucket and deployed infrastructure are intentionally retained.

## Defects found through live testing

- Service creation raced the AWS load balancer admission webhook during initial parallel chart installation. Releases now explicitly depend on the LB release becoming ready; tests also cover disabling that release.
- EBS CSI started before nodes existed, causing a transient degraded add-on. Its Terraform dependency now waits for the EKS module and IRSA policy attachment.
- A subdomain filter excluded its parent Route53 zone. ExternalDNS now enables parent-zone matching while retaining the exact hosted-zone ID and endpoint-domain filters.
- ExternalDNS uses type-prefixed ownership TXT records. Test cleanup now selects those exact names too, with regression coverage preventing unrelated-record deletion.
- Read-only provider lock usage exposed missing Linux platform checksums. Explicit platform locks now cover local development and CI/container architectures.

## Boundaries

- Public ACME issuance was not tested; configure an ACME issuer and its email before requesting public certificates.
- Configure an actual Alertmanager receiver before relying on notifications. Monitoring UIs remain private.
- Loki is optional and disabled in the deployed configuration. Its default filesystem mode is for development and does not include a log collector.
- No application repository was supplied; application GitOps is disabled by default and accepts an immutable commit plus an optional existing authentication Secret.
- Backup testing proves EBS file recovery, not transaction-consistent recovery for an arbitrary database.
- The EKS v20 module emits upstream deprecation warnings for an add-on output attribute; these did not prevent validation, deployment or clean plans. Provider/module major upgrades remain explicit migrations.

Run instructions, upgrade/migration notes and teardown order are in [the README](../readme.md). Local `config.yaml`, `kubeconfig.yaml`, plans and Terraform state are excluded from Git.
