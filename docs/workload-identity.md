# Application workload identity

`workload_identities` is an optional configuration v1 map. Existing configurations create
no additional identities. Each entry binds one namespace/service account pair to an AWS
IRSA role or an Azure user-assigned managed identity. Existing platform controller identities
are unchanged. Cloud permissions remain explicit because AWS and Azure authorization differ.

Add the relevant provider block to your configuration (replace identifiers with your resources):

```yaml
workload_identities:
  reader:
    namespace: application
    service_account: reader
    aws:
      statements:
        - actions: [s3:GetObject]
          resources: [arn:aws:s3:::application-data/settings.json]
    azure:
      role_assignments:
        - scope: /subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/application/providers/Microsoft.Storage/storageAccounts/appdata/blobServices/default/containers/settings
          role_definition_id: /subscriptions/11111111-1111-1111-1111-111111111111/providers/Microsoft.Authorization/roleDefinitions/2a2b9908-6ea1-4ae2-8e65-a410df84e7d1
```

Only the active provider's permissions are provisioned; its block is mandatory for each entry.
Names use lowercase DNS labels; entry keys are at most 24 characters and each subject is
unique. AWS requires concrete actions and resource ARNs without wildcards, and rejects
IAM/account administration and STS role chaining. Azure requires explicit role IDs and
resource/resource-group scopes in the configured subscription; broad Owner, Contributor,
User Access Administrator and RBAC Administrator roles are rejected. Custom roles and other
service roles still require permission review; schema validation does not prove least privilege.

Use the regular `iac.py plan` and reviewed saved-plan `deploy` procedure for `aws/eks` or
`azure/aks`. These stages provision cloud identities without creating Kubernetes namespaces
or applying workloads. Inspect permissions and trust changes before apply. Removing an entry
plans deletion of its identity; renaming its key is not an identity migration.

After deployment, export only public binding fields from the verified target's remote state:

```sh
python3 scripts/iac.py --config config.yaml identities > serviceaccounts.yaml
python3 scripts/iac.py --config config.yaml identities --format json > bindings.json
```

The first command renders ServiceAccounts for your GitOps repository. Create the namespace
through GitOps before reconciling them. The JSON also includes `pod_labels` and `audience`.
Use the account in the workload's pod template:

```yaml
spec:
  template:
    metadata:
      labels:
        azure.workload.identity/use: "true" # AKS only; use pod_labels from the binding
    spec:
      serviceAccountName: reader
      containers:
        - name: application
          image: your-reviewed-image@sha256:YOUR_DIGEST
```

Use an AWS/Azure SDK version supporting web identity credentials. The cloud webhook injects
a projected cloud token and SDK environment variables. `automountServiceAccountToken: false`
disables the unrelated default Kubernetes API token; it does not disable the cloud projection.
Restart existing pods after changing service account annotations. Do not supply static cloud
credentials or enable an IMDS fallback. A workload able to create pods or request tokens as
another service account can use that identity: namespace RBAC and admission policy remain
part of the security boundary (SPEC-005).

Trust is restricted to the exact cluster issuer, subject and cloud audience. AWS sessions
last at most one hour; provider-issued tokens expire normally after permissions/trust are
revoked, so revocation is not an instantaneous purge of existing sessions. Azure role and
federated-credential propagation can take time. Retry boundedly; do not broaden trust to
work around propagation errors. This feature does not grant Kubernetes API RBAC permissions.

For rollback, restore the previous reviewed configuration, inspect the saved plan and apply
only the intended identity changes. This work retains all cloud infrastructure and acceptance
resources until the owner requests their removal.

References: [AWS IRSA setup](https://docs.aws.amazon.com/eks/latest/userguide/associate-service-account-role.html)
and [AKS workload identity setup](https://learn.microsoft.com/en-us/azure/aks/workload-identity-deploy-cluster).

## Live acceptance

`tests/live/workload_identity.py` is opt-in and is excluded from offline unittest discovery.
Use a dedicated `acceptance-reader` entry with namespace `identity-acceptance` and account
`reader`. For AWS grant only `s3:GetBucketLocation` on the configured state bucket ARN.
For Azure grant built-in Reader (`acdd72a7-3385-48ef-bd42-f606fba81ae7`) on the cluster
resource group, with the role definition ID under the configured subscription. The Azure
state resource group must be different and receives no grant. Deploy the reviewed cluster
stage before running:

```sh
uv run --with-requirements requirements.txt --with boto3==1.40.0 python tests/live/workload_identity.py --config config.yaml
```

The test creates and retains two labeled namespaces and three service accounts, refusing
namespaces owned by another manager. It checks webhook mutation using server-side dry-run
(no pod scheduled), requests short-lived Kubernetes tokens and exchanges them directly
with STS/Entra in memory. It tests another account, namespace and audience, then an allowed
read and a denied operation/scope. It never writes or prints credentials. This verifies
real federation and authorization, not a specific application's SDK configuration. No
cloud resources or test namespaces are deleted; keep the identity in the configuration
until an intentional, reviewed removal is authorized.

Acceptance completed on the retained EKS/AKS clusters: all federation and authorization
checks above passed. The changes created five cloud identity resources with no modification
or deletion of existing resources; all seven deployment stages subsequently planned zero
changes. Offline validation passed 77 Python and 14 Terraform tests on macOS ARM64 and
Linux AMD64. The three pre-existing security findings remain tracked in pipeline setup.
