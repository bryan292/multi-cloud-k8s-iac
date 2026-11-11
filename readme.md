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

## Configuration

```bash
cp config.yaml_example config.yaml
```

Set `global.provider` to `aws` or `azure`, complete that provider's block, and set the platform repository plus a published 40-character commit. Keep both provider blocks so switching clouds is only a configuration and credential change.

Security defaults include:

- Kubernetes API access is never open to `0.0.0.0/0`; use trusted `/32` values or private access.
- Both clouds start with at least two nodes and autoscaling.
- EKS workers are private and use IMDSv2 and encrypted storage.
- AKS disables local accounts and run-command and enables Azure RBAC, OIDC, Workload Identity and Cilium.
- Configuration, generated kubeconfig, plans and state are ignored by Git. Never store secrets in either repository.

## Bootstrap state

Authenticate to the selected provider, then use the same commands:

```bash
python3 scripts/preflight.py
python3 scripts/bootstrap.py init
python3 scripts/bootstrap.py plan -out=bootstrap.tfplan
python3 scripts/bootstrap.py apply bootstrap.tfplan
```

Bootstrap state remains local in `bootstrap/terraform.tfstate` or `bootstrap/azure/terraform.tfstate`; back it up securely. State storage has `prevent_destroy` and is retained during cluster teardown.

Azure state uses Entra data-plane authorization with shared keys disabled. AWS state enforces the configured account and enables encryption, versioning, public-access blocking and TLS-only access.

## Deploy and verify

The provider-neutral orchestrator derives the stages from `config.yaml`:

```bash
python3 scripts/deploy.py deploy
python3 scripts/deploy.py verify
```

Every stage applies a saved plan. Preview established stages without applying with:

```bash
python3 scripts/deploy.py plan
```

Stage order is:

- AWS: `aws/network` → `aws/eks` → `kubernetes` → `kube_resources`.
- Azure: `azure/aks` → `kubernetes` → `kube_resources`.

The generated `kubeconfig.yaml` works with kubectl and desktop clients. EKS embeds the configured AWS profile. AKS uses `kubelogin -l azurecli`, so Lens must be able to access a valid Azure CLI login.

Flux CRDs are installed before Terraform creates Flux custom resources. The umbrella repository owns chart versions, provider overlays and environment composition.

## Validation

```bash
scripts/validate.sh
python3 scripts/preflight.py --offline --config config.yaml_example
python3 scripts/preflight.py
python3 scripts/deploy.py verify
```

Static checks cover formatting, schemas, Terraform tests, security constraints and both configuration variants. The umbrella repository independently builds both Kustomize overlays and renders every chart.

Live verification checks ready nodes, cloud control-plane/add-on health, Flux reconciliation and metrics. AWS-only smoke tests additionally cover EBS persistence/backups and ALB/Route53/cert-manager behavior. Azure retains AKS's managed metrics-server and uses `managed-csi`.

Monitoring endpoints are private. Use `kubectl port-forward` and retrieve credentials from Kubernetes Secrets without committing or logging them. Configure production alert receivers and application-aware backups separately.

## Teardown

Destroy cluster stages in reverse order while retaining state storage:

```bash
python3 scripts/deploy.py destroy
```

This is destructive and applies saved destroy plans. Remove application LoadBalancer/Ingress resources while controllers and nodes still exist. Review retained EBS/PV, backup and DNS resources on AWS, and workload-created disks and public IPs on Azure.

## Upgrades

Back up state and application data, upgrade one supported Kubernetes minor at a time, and update chart/provider locks together. Run preflight, review plans for replacements or node rollouts, deploy, and verify Flux and workloads. Migrate state deliberately; never casually repoint an existing key.

See [AWS validation](docs/aws-validation.md) and [Azure validation](docs/azure-validation.md).
