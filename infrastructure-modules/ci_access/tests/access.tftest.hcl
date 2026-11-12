mock_provider "aws" {
  mock_data "aws_vpc" { defaults = { cidr_block = "10.60.0.0/16" } }
  mock_data "aws_ssm_parameter" { defaults = { value = "ami-0123456789abcdef0" } }
}
variables {
  account_id            = "123456789012"
  region                = "us-east-1"
  name                  = "test-access"
  vpc_id                = "vpc-0123456789abcdef0"
  subnet_id             = "subnet-0123456789abcdef0"
  eks_security_group_id = "sg-0123456789abcdef0"
  repository            = "owner/repo"
  environments          = ["aws-dev-apply", "azure-dev-plan"]
  azure_api_cidrs       = ["203.0.113.10/32"]
  endpoints             = { aws = "example.eks.amazonaws.com", azure = "example.azmk8s.io" }
}
run "private_node_and_fixed_destinations" {
  command = apply
  assert {
    condition     = !aws_instance.bridge.associate_public_ip_address && aws_instance.bridge.root_block_device[0].encrypted && aws_instance.bridge.metadata_options[0].http_tokens == "required" && length(aws_security_group.bridge.ingress) == 0
    error_message = "Access node must remain private, encrypted, IMDSv2-only and without ingress."
  }
  assert {
    condition     = toset(aws_security_group_rule.aks_egress.cidr_blocks) == toset(["203.0.113.10/32"]) && aws_security_group_rule.aks_egress.to_port == 443 && length(aws_vpc_endpoint.ssm) == 2 && alltrue([for endpoint in aws_vpc_endpoint.ssm : endpoint.private_dns_enabled])
    error_message = "No internet-wide egress; SSM must use private endpoints and AKS exact /32 addresses."
  }
  assert {
    condition = alltrue([for name, document in aws_ssm_document.tunnel :
      jsondecode(document.content).properties.host == var.endpoints[name] &&
      jsondecode(document.content).properties.portNumber == "443" &&
      jsondecode(document.content).properties.localPortNumber == "8443" &&
      !contains(keys(jsondecode(document.content)), "parameters")
    ])
    error_message = "SSM tunnels must not accept arbitrary hosts or ports."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.tunnel.policy).Statement[0].Condition.BoolIfExists["ssm:SessionDocumentAccessCheck"] == "true" && jsondecode(aws_iam_role_policy.tunnel.policy).Statement[0].Action == ["ssm:StartSession"]
    error_message = "OIDC role must enforce session-document access and cannot execute shell commands."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.tunnel.policy).Statement[2].Action == ["ssm:TerminateSession"] && jsondecode(aws_iam_role_policy.tunnel.policy).Statement[2].Condition.StringLike["ssm:resourceTag/aws:ssmmessages:session-id"] == "$${aws:userid}*" && jsondecode(aws_iam_role_policy.tunnel.policy).Statement[2].Condition.StringEquals["ssm:resourceTag/aws:ssmmessages:target-id"] == aws_instance.bridge.id
    error_message = "Cleanup may terminate only the caller's own sessions on the access node."
  }
  assert {
    condition     = toset(jsondecode(aws_iam_role.github.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"]) == toset(["repo:owner/repo:environment:aws-dev-apply", "repo:owner/repo:environment:azure-dev-plan"])
    error_message = "OIDC subjects must match exact repository and environment names."
  }
}
