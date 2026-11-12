# Multi-cloud Kubernetes IaC

Terraform, Terragrunt and Flux deploy the same Kubernetes platform on either AWS EKS or Azure AKS. Select the cloud with `global.provider` in `config.yaml`; the deployment command does not change.

## Managed stack

| Layer | AWS | Azure |
|---|---|---|
| Remote state | Encrypted/versioned S3 with native locking | Versioned GRS Blob Storage with Microsoft Entra authentication |
| Network | Multi-AZ VPC, private workers, configurable NAT | VNet, node subnet, Azure CNI Overlay |
| Cluster | EKS, managed nodes, IRSA, managed add-ons | AKS, Azure RBAC, Workload Identity, Cilium, managed add-ons |
| Platform | Flux, cert-manager, metrics-server, monitoring, AWS controllers | Flux, cert-manager and monitoring; AKS supplies metrics, load balancing and autoscaling |

Flux reads a pinned umbrella-repository commit and selects `clusters/<environment>/<provider>`. Monitoring uses `gp3` on EKS and `managed-csi` on AKS.

## Requirements

Common tools: Terraform 1.15.1, Terragrunt 1.1.1, Helm 3.x, kubectl compatible with Kubernetes 1.35, Python 3 and PyYAML.

Install the small Python dependency when running outside the provided container:

```bash
python3 -m pip install -r requirements.txt
```

- AWS: AWS CLI and an IAM user or assumed-role profile. Root credentials are rejected.
- Azure: Azure CLI and `kubelogin`. Run `az login`, select the configured subscription, and use an identity allowed to create state resources, networking, role assignments and AKS.
- Publish `platform.commit` to the remote umbrella repository before deployment.

The included container supports validation and AWS workflows. Run Azure deployment on a host where Azure CLI and its authenticated token cache are available.

Start with the [AWS/Azure quickstart](docs/quickstart.md) and [operational runbooks](docs/runbooks.md).

## Configuration

```bash
cp config.aws.yaml_example config.yaml # Or config.azure.yaml_example
```

Set `global.provider` to `aws` or `azure`, complete that provider's block, and set the platform repository plus a published 40-character commit. You can keep both provider blocks or maintain separate configuration files for each cloud.

Security defaults include:

- Kubernetes API access is never open to `0.0.0.0/0`; use trusted `/32` values or private access.
- Both clouds start with at least two nodes and autoscaling.
- EKS workers are private and use IMDSv2 and encrypted storage.
- AKS disables local accounts and run-command and enables Azure RBAC, OIDC, Workload Identity and Cilium.
- Configuration, generated kubeconfig, plans and state are ignored by Git. Never store secrets in either repository.

## Bootstrap state

Authenticate to the selected provider, then use the same commands:

```bash
python3 scripts/iac.py --config config.yaml bootstrap --plan-only
# Review the private log and the emitted run_dir / plan_digest, then:
python3 scripts/iac.py --config config.yaml bootstrap --plan-dir RUN_DIR --plan-digest SHA256
```

Bootstrap state remains local in `bootstrap/terraform.tfstate` or `bootstrap/azure/terraform.tfstate`; back it up securely. State storage has `prevent_destroy` and is retained during cluster teardown. The unified CLI authenticates the destination and verifies saved plans before applying them.

Azure state uses Entra data-plane authorization with shared keys disabled. AWS state enforces the configured account and enables encryption, versioning, public-access blocking and TLS-only access.

## Deploy and verify

The provider-neutral orchestrator derives the stages from `config.yaml`:

```bash
python3 scripts/iac.py --config config.yaml deploy
python3 scripts/iac.py --config config.yaml verify
```

After the cluster verification succeeds, run the live smoke tests for the selected
provider. They create temporary namespaces and cloud resources, then clean up their
test resources even when a check fails:

```bash
export IAC_CONFIG=/absolute/path/to/your-config.yaml
export KUBECONFIG=/absolute/path/to/.iac/targets/DESTINATION_HASH/kubeconfig.yaml
bash scripts/smoke-storage.sh               # AWS gp3 or Azure managed-csi persistence/encryption
TEST_BACKUP=1 bash scripts/smoke-storage.sh # AWS only: also restore and verify an AWS Backup snapshot
python3 scripts/smoke-ingress.py            # AWS only: ALB, exact Route53 records, certificate
python3 scripts/smoke-service.py            # Azure only: LoadBalancer HTTP and certificate
```

External HTTP tests require configured trusted administrative CIDRs and restrict
their load balancer access to those ranges. Certificates use a test self-signed
issuer; these checks do not claim public ACME validation. Inspect the test logs if
cleanup fails before proceeding with cluster teardown.

Every stage applies a saved plan. Preview established stages without applying with:

```bash
python3 scripts/iac.py --config config.yaml plan
```

Stage order is:

- AWS: `aws/network` → `aws/eks` → `kubernetes` → `kube_resources`.
- Azure: `azure/aks` → `kubernetes` → `kube_resources`.

The generated `.iac/targets/<destination-hash>/kubeconfig.yaml` works with kubectl and desktop clients. Set `KUBECONFIG` to that file before running the standalone smoke tests or opening Lens. EKS embeds the configured AWS profile. AKS uses `kubelogin -l azurecli`, so Lens must be able to access a valid Azure CLI login.

Flux CRDs are installed before Terraform creates Flux custom resources. The umbrella repository owns chart versions, provider overlays and environment composition.

Deployment CI uses GitHub-hosted runners with [restricted SSM access](docs/hosted-runner-access.md).

See [operation acceptance](docs/operations-validation.md), [pipeline setup](docs/pipeline.md) and [operation commands and recovery](docs/operations.md) for saved-plan review, reattempts, diagnostics and private artifacts. `scripts/deploy.py` remains a compatibility alias for the unified CLI.

## Validation

```bash
scripts/validate.sh
python3 scripts/preflight.py --offline --config config.yaml_example
python3 scripts/preflight.py
python3 scripts/iac.py --config config.yaml verify
```

Static checks cover formatting, schemas, Terraform tests, security constraints and both configuration variants. The umbrella repository independently builds both Kustomize overlays and renders every chart.

Live verification checks ready nodes, cloud control-plane/add-on health, Flux reconciliation and metrics. AWS-only smoke tests additionally cover EBS persistence/backups and ALB/Route53/cert-manager behavior. Azure retains AKS's managed metrics-server and uses `managed-csi`.

Monitoring endpoints are private. Use `kubectl port-forward` and retrieve credentials from Kubernetes Secrets without committing or logging them. Configure production alert receivers and application-aware backups separately.

## Teardown

Destroy cluster stages in reverse order while retaining state storage:

```bash
python3 scripts/iac.py --config config.yaml destroy --confirm-destroy PROVIDER/ENVIRONMENT/CLUSTER
```

This is destructive and applies saved destroy plans. Remove application LoadBalancer/Ingress resources while controllers and nodes still exist. Review retained EBS/PV, backup and DNS resources on AWS, and workload-created disks and public IPs on Azure.

## Upgrades

Back up state and application data, upgrade one supported Kubernetes minor at a time, and update chart/provider locks together. Run preflight, review plans for replacements or node rollouts, deploy, and verify Flux and workloads. Migrate state deliberately; never casually repoint an existing key.

See [AWS validation](docs/aws-validation.md) and [Azure validation](docs/azure-validation.md).

### Versioned configuration and migration

Configuration declares `schema_version: 1`. The offline contract lives in
`schemas/config-v1.json`; install `requirements.txt` before running the scripts.
Use `config.aws.yaml_example` or `config.azure.yaml_example` and replace the sample
identities, repository and commit. `config.yaml_example` keeps both provider blocks
for compatibility. Only the selected cloud's blocks are required. Unknown fields,
mutable commits, invalid scaling and unrestricted administrative CIDRs are rejected.
Do not put passwords, tokens or private keys in YAML; use cloud CLI authentication
and existing Kubernetes Secret names.

For an existing unversioned configuration:

```sh
python3 scripts/migrate-config.py config.yaml > config.v1.yaml
python3 scripts/preflight.py --offline --config config.v1.yaml
# Alternatively, explicitly replace config.yaml and retain config.yaml.bak:
python3 scripts/migrate-config.py config.yaml --in-place
```

The migrator preserves resource names and backend coordinates, refuses unknown
fields or unsupported versions, and never overwrites an existing backup. To roll
back, restore `config.yaml.bak` together with the previous script version. The
current scripts require v1; migration does not move Terraform state.

To switch clouds, prepare and validate a separate provider configuration, then
select it with `--config PATH`. Retain the original configuration for its resources;
changing `global.provider` does not migrate or destroy them. The deployment wrapper checks identity, backend ownership/location and initialized
backend metadata before invoking any plan (including destroy). Bootstrap checks
identity and its existing local state; it can create a backend that does not exist yet.
Run `scripts/preflight.py` for the additional Kubernetes/add-on compatibility checks.

The wrappers use the configured AWS profile or the current Azure CLI login for both
checks and Terraform. Alternate credential environment variables are removed from
the child process; variable/state/backend CLI overrides are rejected. Direct invocation
of Terraform or Terragrunt bypasses these wrapper checks and should be reserved for
reviewed recovery procedures. Terragrunt cannot automatically create/update the
state bucket through the deployment wrapper; create it through bootstrap.

Verified destinations are pinned locally in the ignored `.deployment-targets/`
directory, separately for bootstrap/deployment and each provider, cluster and
environment. A changed account, subscription or backend is rejected. Restore the
original configuration for ordinary operation. For an intentional state migration,
back up state, review the source/destination, migrate explicitly, and only then archive
the corresponding local pin and stale initialized cache. Removing a pin does not
migrate state, and fresh clones do not inherit these local pins.

The offline render tests use isolated copies and outputs simulated only for `render`.
Actual plans require applied dependency outputs: an EKS plan needs the AWS network,
and Flux/platform plans need a running cluster. The wrapper does not invent outputs
or apply infrastructure while running `plan`.


Validation references: [S3 bucket ownership checks](https://docs.aws.amazon.com/cli/latest/reference/s3api/head-bucket.html),
[S3 naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html),
[Azure resource names](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-name-rules),
and [Azure container checks with CLI login](https://learn.microsoft.com/en-us/cli/azure/storage/container#az-storage-container-exists).

Application cloud access: [workload identity configuration and GitOps bindings](docs/workload-identity.md).

Platform telemetry and controlled alert acceptance: [observability](docs/observability.md).

Read-only platform diagnosis: [checks and output contract](docs/diagnostics.md).
