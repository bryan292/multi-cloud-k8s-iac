# GitHub-hosted runner access to EKS and AKS

The deployment workflow runs on GitHub's `ubuntu-24.04` machines. It reaches Kubernetes
through an AWS Systems Manager tunnel; the EC2 access node is **not** a self-hosted runner.
It executes no repository code and accepts no inbound connections.

## Connection and authorization

1. The job obtains temporary AWS credentials through GitHub OIDC for the tunnel role.
   Trust is restricted to the exact repository and configured environment subjects.
2. Session Manager forwards local port 8443 through the private access node to one fixed
   Kubernetes hostname on port 443. Separate documents select AWS or Azure. Neither host
   nor port is a caller-supplied document parameter.
3. The job obtains its separate AWS or Azure deployment identity, generates kubeconfig,
   and preserves the cluster CA and original TLS hostname while changing the connection
   address to `https://127.0.0.1:8443`. No TLS verification is disabled.
4. Terraform Helm/Kubernetes providers and kubectl use that kubeconfig. Cloud management
   APIs continue using their ordinary authenticated HTTPS connections.
5. An `always()` step tells the tunnel supervisor to terminate its own SSM session explicitly, then close its client processes. Failed remote cleanup is reported and blocks reuse of that job directory. SSM documents enforce a 15-minute idle timeout and a two-hour maximum; the supervisor also has a two-hour deadline. Closing a tunnel does not remove
   the access node, clusters or any other infrastructure.

The role permits StartSession only for the configured node and fixed session documents.
`ssm:SessionDocumentAccessCheck` is enforced, preventing a fallback to the default shell
document. It does not grant SendCommand or SSH forwarding. TerminateSession requires both the access-node tag and the caller's own session identity tag; it cannot close another job's sessions. Tunnel-role credentials last up to two hours so cleanup remains authorized throughout the job. Cloud IAM and Kubernetes RBAC
remain necessary in addition to tunnel access. See the [AWS Session Manager documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
and [Kubernetes kubeconfig TLS configuration](https://kubernetes.io/docs/reference/config-api/kubeconfig.v1/).

## Access infrastructure

`infrastructure-modules/ci_access` creates the small private EC2 node, its SSM instance
profile, fixed forwarding documents and GitHub OIDC role. It can reuse an existing GitHub
OIDC provider via `oidc_provider_arn`. The instance has an encrypted disk, IMDSv2, no public
IP and no security-group ingress; `prevent_destroy` protects it from routine teardown.
Private interface endpoints provide SSM and ssmmessages connectivity. The existing NAT supplies only the AKS API connection. Node egress is limited to the SSM endpoint security group, the EKS control-plane security group and individually resolved AKS API `/32` addresses. Private endpoint ingress preserves TLS access for existing VPC clients; IAM authorization remains required. An explicit security-group rule allows
only the node to reach the EKS API. AKS's API allowlist includes that NAT's single public
`/32`, alongside the previous administrative ranges.

Inputs identify the existing VPC/subnet, EKS API security group, both API hostnames,
repository, exact environment names and `azure_api_cidrs` (the current API IPv4 addresses, each `/32`). Review these destinations before applying.
The module's local state and reviewed plans are private under `.iac/ci-access/`; back up
`terraform.tfstate` securely. Example commands, with your prepared private inputs:

```sh
terraform -chdir=infrastructure-modules/ci_access init -lockfile=readonly
terraform -chdir=infrastructure-modules/ci_access plan -state=/ABS/.iac/ci-access/terraform.tfstate -var-file=/ABS/.iac/ci-access/inputs.tfvars.json -out=/ABS/.iac/ci-access/access.tfplan
terraform -chdir=infrastructure-modules/ci_access apply -state=/ABS/.iac/ci-access/terraform.tfstate /ABS/.iac/ci-access/access.tfplan
```

Keep node state separate from cluster state and retain the existing administrative CIDRs.
If a cluster is recreated and its hostname changes, update the fixed SSM document through
a reviewed access-module plan. Do not replace it with an arbitrary forwarding document.
If the NAT is replaced, update its exact `/32` in AKS configuration before relying on it. If AKS changes its API IP addresses, update `azure_api_cidrs` through a reviewed access-module plan. This deliberately fails closed on an unexpected endpoint change.
A failure of the access node affects CI connectivity; it does not remove cluster resources.

## Environment variables

Each GitHub environment needs the module's `role_arn` as `TUNNEL_ROLE_ARN`, its AWS region
as `TUNNEL_REGION`, `instance_id` as `TUNNEL_INSTANCE_ID`, and the correct entry from
`documents` as `TUNNEL_DOCUMENT`. Deployment roles, configuration/encryption secrets and
owner-only approval gates remain separate requirements described in [pipeline setup](pipeline.md).
The access node and role are provisioned. All four dev GitHub environments have verified
tunnel variables and the owner as sole reviewer for plan and apply. Branch protection,
deployment identities/secrets, verification of administrator bypass and remote GitHub
acceptance remain pending. No workflow has been published by this local change.

## Acceptance evidence

Real local sessions through the restricted documents reached two Ready nodes in each
cloud with certificate verification enabled. For both clouds, Helm and Kubernetes plans
through the tunnel returned zero changes. IAM simulation allowed the intended sessions
and denied a failed document-access check, an SSH document and SendCommand. Ubuntu 24.04
executed the pinned Linux tooling successfully. These checks validate the network path and
tooling; they do not replace an eventual GitHub-issued OIDC token acceptance run.

Final validation passed 71 Python and 10 Terraform tests on macOS ARM64 and Linux AMD64.
Both clouds rejected an incorrect TLS hostname. Explicit remote cleanup left zero active
SSM sessions; IAM simulation rejected termination of another job or node session. The
final security scan reports the three pre-existing findings documented in pipeline setup,
zero secrets and no finding in the access module.

All access infrastructure is retained until the owner explicitly requests its removal.

## Later teardown, only when authorized

The access module holds dependencies on the AWS VPC and the EKS security group. When the
owner eventually requests removal, retire this access module deliberately before removing
the referenced cluster/network; its `prevent_destroy` guard must be changed intentionally
as part of that reviewed teardown. Cluster-only teardown cannot cleanly remove the VPC
while the access instance and private endpoints still use it. No such teardown is run by
the deployment workflow or by tunnel cleanup.
