# Reviewed cloud pipeline

`validate.yml` validates pull requests without cloud credentials. It checks Terraform,
Python and documentation, scans high/critical IaC findings and secrets, and produces a
CycloneDX dependency SBOM. Actions are pinned by commit; updates require review.
`cloud-operation.yml` runs that validation before a manually requested single-stage plan.
It deliberately has no destroy job and does not bootstrap local state on ephemeral runners.

## External setup required before activation

The repository owner must configure the following; adding the workflow alone does not
create an approval boundary or grant cloud access:

- Jobs use GitHub-hosted `ubuntu-24.04` runners. `ci/install-tools.sh` installs the
  Terraform/Terragrunt/Helm/kubectl versions from the checksum-verified container build,
  Python requirements, Session Manager plugin 1.2.896.0 and kubelogin 0.2.22. Additional
  downloads have pinned SHA256 checks. The runner's Azure CLI, AWS CLI, GitHub CLI and GPG
  must be present; installation fails if they are absent.
- Deploy the restricted [SSM access module](hosted-runner-access.md) into the existing
  AWS private subnet. The hosted runner opens a fixed-destination tunnel for Kubernetes
  stages. It does not require inbound SSH or a GitHub IP allowlist. Both provider jobs
  use the restricted AWS tunnel role via OIDC before logging into their deployment role.
- In each environment configure `TUNNEL_ROLE_ARN`, `TUNNEL_REGION`, `TUNNEL_INSTANCE_ID`
  and the provider-specific `TUNNEL_DOCUMENT`. These are identifiers, not credentials.
- For each destination, create `<provider>-<environment>-plan` and
  `<provider>-<environment>-apply` GitHub Environments. Restrict deployment branches to the
  default branch. Set the personal repository owner (`bryan292` for this repository) as the only required reviewer for `apply`. Allow self-review so the owner can approve a run they started; approval remains manual. Disable administrator bypass. An API check fails closed if the sole-owner reviewer policy, self-review setting or branch protection are absent or cannot be read. Administrator bypass must be disabled and checked in the GitHub settings UI; the documented environment REST response does not expose that setting. Protect changes to workflows and `ci/` through
  branch protection/code review. The workflow fails closed on non-default-branch dispatch.
- In both environments store `IAC_CONFIG_JSON` as a secret containing the same validated
  configuration. Store the same randomly generated, single-line `PLAN_ENCRYPTION_KEY`
  (at least 32 characters). This encrypts artifacts; it is not a cloud access credential.
- AWS: environment variables `AWS_ROLE_ARN` and `AWS_REGION`. Configure GitHub OIDC trust
  for the exact repository and environment subject, audience `sts.amazonaws.com`. Use
  separate plan/apply roles; plan needs state locking/read and provider read permissions,
  apply needs only the managed resource permissions. The apply role needs a two-hour
  maximum session duration. Temporary OIDC credentials are placed in a private profile
  matching `aws.profile`, then removed at job end.
- Azure: environment variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and
  `AZURE_SUBSCRIPTION_ID`. Configure exact repository/environment federated subjects,
  audience `api://AzureADTokenExchange`, and narrowly scoped plan/apply role assignments.
  Grant Blob data-plane access for the configured state. Local admin credentials are unused.

The four dev environments (`aws-dev-plan`, `aws-dev-apply`, `azure-dev-plan`,
`azure-dev-apply`) are now configured with the repository owner as sole required reviewer
for both plan and apply, self-review allowed, protected-branches policy and verified tunnel
variables. The default branch is currently unprotected: the workflow approval-policy check
therefore rejects execution. The environment policy alone is not a substitute for creating
branch protection. Administrator bypass has not been verified in the settings UI.
Deployment roles and configuration/encryption secrets still require setup. A real GitHub
acceptance run remains pending; no workflow has been published or dispatched by this change.
The access node and tunnel OIDC role have been provisioned and tested locally; this does
not claim a completed GitHub-issued OIDC execution.

## Review procedure

Dispatch one valid stage for the provider and environment. Review its counts and manifest
SHA256 in the plan job summary. To inspect resource-level changes, download the encrypted
artifact, decrypt it locally with GPG and inspect the private Terraform log/binary plan.
Do not paste decrypted contents into GitHub comments or tickets.

Approve the `apply` environment only after that review. Apply downloads the exact artifact
ID from the same run, checks its encrypted digest, decrypts it, validates the manifest and
uses the saved binary plan. Configuration/source changes, altered artifacts, stale state or
changed dependency outputs block the apply. Never re-plan silently after approval.

Run foundation stages first, then Flux and platform stages. The final `kube_resources`
stage invokes full verification. Earlier stages do not claim a complete healthy platform.
A fresh runner regenerates a private kubeconfig for existing-cluster stages through cloud
CLI user authentication, then points it at the loopback tunnel while preserving the
original TLS hostname and CA. Binary plans remain tied to the same source and absolute paths.

Artifacts expire after one day. Local plans, logs, snapshots and temporary credentials are
removed even on failure. The tunnel supervisor explicitly terminates its own SSM session and closes its client processes; the access
node and all cluster resources are retained. Preserve encrypted evidence before
expiry when investigating a failed apply. Retry with a new reviewed plan after checking
actual state. A GitHub rerun is not equivalent to a local `--resume` operation.

The SBOM covers discovered repository dependencies; it does not claim coverage of every
remote Terraform module, Helm image or underlying OS package. Container/image vulnerability
coverage and module provenance must be extended before claiming a complete supply-chain inventory.

## Initial security baseline

The first local scan identified existing infrastructure findings that still block
this strict gate: public network reachability of the Azure state account (Entra authorization
is enforced), S3 state encryption using an AWS-managed rather than customer-managed key,
and the upstream EKS module's unrestricted node egress. The access node uses private SSM endpoints and scoped EKS/AKS egress; no scanner exception is used. No suppression was added. Changes
to state networking/encryption and node egress require dedicated plans and live acceptance;
the pipeline must not be described as production-ready until these findings are resolved
or explicitly accepted through a reviewed, scoped, expiring exception.

The container's root-user finding was corrected by setting a dedicated non-root user.
Trivy filtering, if later required, must follow its [official exception format](https://trivy.dev/docs/dev/configuration/filtering/).

Approval checks follow the [GitHub environment API](https://docs.github.com/en/rest/deployments/environments); the administrator bypass setting follows [GitHub deployment review documentation](https://docs.github.com/en/actions/how-tos/managing-workflow-runs-and-deployments/managing-deployments/reviewing-deployments).
