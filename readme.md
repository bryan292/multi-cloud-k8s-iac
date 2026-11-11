# AWS EKS infrastructure

Terraform + Terragrunt deploy an AWS VPC, EKS, managed nodes, EBS storage, Flux and platform controllers. AWS is the implemented cloud provider; the repository name does not imply working Azure/GCP modules.

## Requirements

- Docker with Compose, or Terraform 1.15.1, Terragrunt 1.1.1, Helm 3.19.0, kubectl 1.35.x, AWS CLI and Python 3 with PyYAML.
- An AWS IAM user or role profile with infrastructure deployment permissions. Root credentials are rejected by preflight. Temporary credentials / SSO are preferred.
- An existing public Route53 hosted zone when DNS or certificates are enabled.
- A runner with network access to the EKS endpoint. The default endpoint is private; for local execution configure a trusted public `/32`.

The container supports ARM64 and AMD64, verifies tool checksums and mounts `~/.aws` read-only. It does not bake source files or credentials into the image.

```bash
cp .env_sample .env
cp config.yaml_example config.yaml
# Edit config.yaml: account, globally unique bucket, admin principal/CIDR, DNS, capacity.
docker compose build
docker compose run --rm terraform-container
```

Set `AWS_PROFILE` to the deployment profile (Compose defaults to `bryan`). Both the AWS providers and state backend enforce the configured account ID. `config.yaml`, plans, kubeconfig and state files are ignored by Git.

The generated kubeconfig embeds `global.aws_profile` in its exec environment. This lets desktop clients such as Lens request EKS tokens with the intended identity even when they do not inherit `AWS_PROFILE` from your terminal.

## Deployment

From the repository root:

```bash
python3 scripts/preflight.py
python3 scripts/bootstrap.py init
python3 scripts/bootstrap.py plan -out=bootstrap.tfplan
# Review the plan, then create the protected state bucket.
python3 scripts/bootstrap.py apply bootstrap.tfplan
```

Bootstrap manages S3 versioning, encryption, public access blocking and a TLS-only policy. Its local state is in `bootstrap/terraform.tfstate`: back it up securely. The bucket has `prevent_destroy` and is intentionally independent of the cluster lifecycle. Import an existing bucket and its companion resources instead of trying to recreate it.

Deploy in order; each apply uses a saved, reviewed plan:

```bash
cd deployment-config/aws/network
terragrunt run -- plan -out=network.tfplan
terragrunt run -- apply network.tfplan
cd ../eks
terragrunt run -- plan -out=eks.tfplan
terragrunt run -- apply eks.tfplan
cd ../../kubernetes
terragrunt run -- plan -out=flux.tfplan
terragrunt run -- apply flux.tfplan
cd ../kube_resources
terragrunt run -- plan -out=resources.tfplan
terragrunt run -- apply resources.tfplan
cd ../..
export KUBECONFIG="$PWD/kubeconfig.yaml"
python3 scripts/verify-cluster.py
```

The separate Flux apply installs its CRDs before Terraform plans `kubernetes_manifest` resources. On a fresh account, do not attempt one monolithic plan across all stages. A successful final Terraform apply means manifests were accepted; `verify-cluster.py` also waits for Flux reconciliation and workload readiness.

## Configuration and defaults

| Area | Configuration / behavior |
|---|---|
| State | `global.bucket_name`, `state_region`; S3 native locking (`use_lockfile`), encryption and versioning. Existing `~cluster/environment/unit` key structure is preserved. |
| Network | `network.vpc_cidr`, two or three AZs, private workers, isolated control-plane subnets, VPC flow logs retained 30 days. NAT per AZ by default; single NAT is an explicit cost/availability tradeoff. |
| Access | `eks.admin_principal_arns` contains permanent IAM user/role ARNs, including the deployment identity. No implicit cluster-creator admin. `admin_cidrs: []` means private-only endpoint; never use `/0`. |
| Nodes | AL2023, IMDSv2 required, encrypted gp3 root disks, two On-Demand nodes by default, configurable instance types and scaling. Spot remains an opt-in tradeoff. |
| Add-ons | Kubernetes 1.35 baseline; CoreDNS, kube-proxy, VPC CNI and EBS CSI. `eks.addon_versions` can pin compatible versions listed by preflight; empty values use AWS's creation-time defaults. |
| Storage | Explicit `gp3` StorageClass, encryption, `WaitForFirstConsumer`, expansion, `Retain`. Select `storageClassName: gp3` in workloads. |
| Backups | Daily AWS Backup snapshots of this cluster's tagged EBS volumes, 30-day retention. This does not back up Kubernetes objects or replace application-consistent database backups. |
| Platform | Terraform bootstraps an immutable `platform.repository` commit. Flux then reconciles `clusters/<environment>` from the umbrella repository, which owns chart pins, values, dependencies and environment composition. |
| Monitoring | Prometheus, Alertmanager and private Grafana with persistent volumes. EKS-inaccessible control-plane scrape targets are disabled. Configure alert receivers in the umbrella environment before production. |
| DNS | ExternalDNS is restricted to the hosted zone and domain, uses a cluster-specific TXT owner, and defaults to `upsert-only`. |
| Certificates | cert-manager and scoped Route53 IAM permissions are installed. Create an ACME ClusterIssuer with your email and intended staging/production endpoint before requesting public certificates. |
| Logs | Optional Loki single-instance filesystem configuration for development; use S3, appropriate replication and a log collector for production. |
| Application | The umbrella repository composes environment applications. An additional application repository can optionally be reconciled from an HTTPS URL pinned to a 40-character commit. Private Git authentication uses an existing Secret. |

Do not put secrets in either repository. Use existing Kubernetes Secrets or SOPS-encrypted manifests. IAM role ARNs and other environment settings belong in the umbrella environment's `cluster-settings` ConfigMap.

Grafana and monitoring endpoints are not public. Use `kubectl port-forward` and retrieve credentials from the generated Kubernetes Secret without committing or logging them. Network policies and Pod Security rules for application namespaces must be designed for the applications' actual traffic and permissions.

## Validation

```bash
scripts/validate.sh
python3 scripts/preflight.py --offline --config config.yaml_example
python3 scripts/preflight.py
```

Validation covers formatting, provider schemas, mocked Terraform plans (no AWS writes), invalid access/scaling inputs and example configuration. The umbrella repository independently builds every Kustomize root and renders every pinned chart. CI runs both repositories' checks without AWS credentials. Lock files and module/provider versions are tracked; upgrades must update pins, lock files and tests together.

For live checks, `scripts/verify-cluster.py` verifies ready nodes, active EKS add-ons, current HelmRelease reconciliation, and metrics. `scripts/smoke-storage.sh` creates an isolated PVC/pod, writes data, recreates the pod and checks persistence; it deletes its own PVC and EBS volume afterward. `scripts/smoke-ingress.py` verifies ALB HTTP routing, a Route53 alias from ExternalDNS and self-signed certificate issuance, then removes its unique test namespace, load balancer and DNS records. It does not prove public ACME issuance. Run `TEST_BACKUP=1 scripts/smoke-storage.sh` to additionally create an AWS Backup recovery point, restore a new EBS volume from its snapshot and verify the original data; only the test recovery point and test volumes are removed afterward.

## Upgrade and migration

1. Back up Terraform state and application data. Run preflight with the target version and pin compatible EKS add-ons.
2. Upgrade supported EKS minor versions sequentially. Update kubectl and the autoscaler chart/image together; the current preflight intentionally rejects an autoscaler/Kubernetes mismatch.
3. Review saved plans for replacements, node rollouts and IAM access changes. Ensure the deployment principal remains an EKS administrator.
4. Apply AWS stages, then Flux, then platform manifests. Confirm reconciliation and run live smoke tests.

Existing deployments use a non-destructive ownership migration: Terraform removes its HelmRepository and HelmRelease addresses from state with `destroy = false`, then Flux reconciles the same objects from the immutable umbrella commit. Review the plan and confirm it contains forget actions rather than deletions. Monitoring volumes and namespaces must remain intact. The AMI/capacity changes roll nodes. Provider major versions are deliberately constrained to the tested EKS v20/AWS v5 combination rather than silently changing the existing state schema.

S3 native locking replaces the legacy DynamoDB lock configuration. Stop old runners before migrating and ensure every runner uses the new backend settings. Moving from `env` to `deployment-config` does not itself justify creating a new state: verify the bucket and exact key before init; use `terraform init -migrate-state` for intentional backend moves.

## Restore and teardown

Recover Terraform state from an S3 object version only after stopping all writers; preserve the current version first. Recover EBS data through AWS Backup into the intended availability zone, then bind a static CSI PV/PVC to the restored volume and validate application data. Recreate Kubernetes objects from Git. Perform restore drills; a scheduled backup alone is not proof of recoverability.

For teardown, first remove application Ingress/LoadBalancer Services and wait for AWS load balancer cleanup. Delete Flux-managed applications and releases while controllers and nodes still run. Destroy in reverse order: `kube_resources`, `kubernetes`, `aws/eks`, `aws/network`. Use a reviewed `terragrunt run -- plan -destroy -out=destroy.tfplan` and apply that plan in each directory.

Retained PVs/EBS volumes, nonempty backup vaults and DNS records from `upsert-only` need explicit review. Do not delete backups to force teardown. Keep the state bucket and bootstrap state. EKS, NAT gateways, nodes, storage, backups and CloudWatch incur charges while deployed.

## Validation record

See [the AWS validation report](docs/aws-validation.md) for live test results and remaining environment-specific configuration. The load balancer IAM policy is vendored from [upstream v3.6.2](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/v3.6.2/docs/install/iam_policy.json) and must be updated together with its chart pin.
