terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers { aws = { source = "hashicorp/aws", version = "5.100.0" } }
}
variable "account_id" { type = string }
variable "region" { type = string }
variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_id" { type = string }
variable "eks_security_group_id" { type = string }
variable "repository" { type = string }
variable "environments" { type = set(string) }
variable "endpoints" {
  type = map(string)
  validation {
    condition     = alltrue([for host in values(var.endpoints) : can(regex("^[a-zA-Z0-9][a-zA-Z0-9.-]+$", host))]) && toset(keys(var.endpoints)) == toset(["aws", "azure"])
    error_message = "Provide exact AWS/Azure API hostnames without paths, ports or wildcards."
  }
}
variable "azure_api_cidrs" {
  type = set(string)
  validation {
    condition = length(var.azure_api_cidrs) > 0 && alltrue([
      for cidr in var.azure_api_cidrs : can(cidrhost(cidr, 0)) && endswith(cidr, "/32")
    ])
    error_message = "Use only individually resolved AKS API IPv4 /32 addresses."
  }
}
variable "oidc_provider_arn" {
  type    = string
  default = null
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags { tags = { ManagedBy = "Terraform", Purpose = "GitHub Kubernetes tunnel" } }
}
data "aws_ssm_parameter" "ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
resource "aws_security_group" "bridge" {
  name_prefix = "${var.name}-"
  description = "SSM access node: no incoming connections"
  vpc_id      = var.vpc_id

}
resource "aws_security_group" "ssm" {
  name_prefix = "${var.name}-ssm-"
  description = "Private SSM endpoints for the access node"
  vpc_id      = var.vpc_id
}
resource "aws_security_group_rule" "ssm_ingress" {
  description              = "SSM TLS from access node only"
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.ssm.id
  source_security_group_id = aws_security_group.bridge.id
}
resource "aws_security_group_rule" "ssm_egress" {
  description              = "SSM TLS to private endpoints only"
  type                     = "egress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.bridge.id
  source_security_group_id = aws_security_group.ssm.id
}
resource "aws_security_group_rule" "eks_egress" {
  description              = "TLS to EKS control plane only"
  type                     = "egress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.bridge.id
  source_security_group_id = var.eks_security_group_id
}
resource "aws_security_group_rule" "aks_egress" {
  description       = "TLS to individually resolved AKS API addresses only"
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  security_group_id = aws_security_group.bridge.id
  cidr_blocks       = var.azure_api_cidrs
}
resource "aws_vpc_endpoint" "ssm" {
  for_each            = toset(["ssm", "ssmmessages"])
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [var.subnet_id]
  security_group_ids  = [aws_security_group.ssm.id]
  private_dns_enabled = true
}
resource "aws_security_group_rule" "eks" {
  description              = "Kubernetes API from SSM access node only"
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = var.eks_security_group_id
  source_security_group_id = aws_security_group.bridge.id
}
resource "aws_iam_role" "node" {
  name = "${var.name}-node"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_instance_profile" "node" {
  name = "${var.name}-node"
  role = aws_iam_role.node.name
}
resource "aws_instance" "bridge" {
  ami                         = nonsensitive(data.aws_ssm_parameter.ami.value)
  instance_type               = "t3.micro"
  subnet_id                   = var.subnet_id
  associate_public_ip_address = false
  vpc_security_group_ids      = [aws_security_group.bridge.id]
  iam_instance_profile        = aws_iam_instance_profile.node.name
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 8
  }
  tags = { Name = var.name }
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [ami]
  }
  depends_on = [aws_iam_role_policy_attachment.ssm]
}
resource "aws_ssm_document" "tunnel" {
  for_each        = var.endpoints
  name            = "${var.name}-${each.key}"
  document_type   = "Session"
  document_format = "JSON"
  content = jsonencode({
    schemaVersion = "1.0", description = "Kubernetes API only; no shell or arbitrary forwarding", sessionType = "Port",
    inputs        = { idleSessionTimeout = "15", maxSessionDuration = "120" },
    properties    = { type = "LocalPortForwarding", host = each.value, portNumber = "443", localPortNumber = "8443" }
  })
}
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.oidc_provider_arn == null ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}
resource "aws_iam_role" "github" {
  max_session_duration = 7200
  name                 = "${var.name}-github"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Federated = coalesce(var.oidc_provider_arn, try(aws_iam_openid_connect_provider.github[0].arn, null)) },
    Action = "sts:AssumeRoleWithWebIdentity", Condition = { StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub" = [for environment in var.environments : "repo:${var.repository}:environment:${environment}"]
    } }
  }] })
}
resource "aws_iam_role_policy" "tunnel" {
  role = aws_iam_role.github.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ssm:StartSession"], Resource = concat([aws_instance.bridge.arn], [for document in aws_ssm_document.tunnel : document.arn]), Condition = { BoolIfExists = { "ssm:SessionDocumentAccessCheck" = "true" } } },
    { Effect = "Allow", Action = ["ssmmessages:OpenDataChannel"], Resource = "arn:aws:ssm:${var.region}:${var.account_id}:session/*" },
    { Effect = "Allow", Action = ["ssm:TerminateSession"], Resource = "arn:aws:ssm:${var.region}:${var.account_id}:session/*", Condition = {
      StringEquals = { "ssm:resourceTag/aws:ssmmessages:target-id" = aws_instance.bridge.id },
      StringLike   = { "ssm:resourceTag/aws:ssmmessages:session-id" = "$${aws:userid}*" }
    } }
  ] })
}
output "instance_id" { value = aws_instance.bridge.id }
output "role_arn" { value = aws_iam_role.github.arn }
output "documents" { value = { for provider, document in aws_ssm_document.tunnel : provider => document.name } }
# Private DNS applies to the VPC. Preserve authenticated SSM access for existing
# VPC clients; this does not grant IAM permissions or open the access node.
data "aws_vpc" "selected" { id = var.vpc_id }
resource "aws_security_group_rule" "ssm_vpc_clients" {
  description       = "Preserve SSM TLS for existing VPC clients after enabling private DNS"
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  security_group_id = aws_security_group.ssm.id
  cidr_blocks       = [data.aws_vpc.selected.cidr_block]
}
