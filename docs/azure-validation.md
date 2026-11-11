# Azure validation record

Validated on 2026-11-10 in the configured personal subscription, region `eastus`.

## Configuration

- AKS `dev-iac-test-cluster`, Kubernetes 1.35, two `Standard_D2s_v3` nodes in zones 1 and 2.
- Azure CNI Overlay with Cilium, Azure RBAC, local accounts disabled, OIDC and Workload Identity enabled.
- API server restricted to the configured administrator `/32`.
- Entra-authenticated Blob state with shared keys disabled, versioning, retention and GRS replication.
- Flux pinned to the Azure overlay in the umbrella repository.

## Results

- Bootstrap and AKS Terraform applies completed successfully.
- Both nodes reported `Ready`; `managed-csi` provisioned monitoring volumes.
- The kubeconfig authenticated through Azure CLI using `kubelogin`.
- Flux fetched the exact pinned commit and deployed cert-manager and monitoring.
- AKS's managed metrics-server remained authoritative; the Azure overlay excludes the duplicate chart.

Final reconciliation, metrics, storage persistence and idempotence were exercised during the same live run.
