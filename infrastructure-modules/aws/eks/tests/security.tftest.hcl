mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { arn = "arn:aws:iam::123456789012:role/test", account_id = "123456789012" } }
  mock_data "aws_iam_session_context" { defaults = { issuer_arn = "arn:aws:iam::123456789012:role/test" } }
  mock_data "aws_partition" { defaults = { partition = "aws", dns_suffix = "amazonaws.com" } }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}
mock_provider "tls" {}
mock_provider "time" {}
mock_provider "local" {}
mock_provider "null" {}
mock_provider "cloudinit" {}
variables {
  cluster_name             = "test-cluster"
  environment              = "test"
  account_id               = "123456789012"
  aws_profile              = "test"
  region                   = "us-east-1"
  tags                     = {}
  vpc_id                   = "vpc-0123456789abcdef0"
  subnet_ids               = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]
  control_plane_subnet_ids = ["subnet-0123456789abcdef2", "subnet-0123456789abcdef3"]
  kubernetes_version       = "1.35"
  hosted_zone_id           = "Z123456789"
  terragrunt_dir           = "/tmp/eks-test/deployment-config/aws/eks"
  admin_principal_arns     = ["arn:aws:iam::123456789012:role/test"]
}
run "secure_plan" { command = plan }
run "reject_public_internet" {
  command = plan
  variables { admin_cidrs = ["0.0.0.0/0"] }
  expect_failures = [var.admin_cidrs]
}
run "reject_invalid_scaling" {
  command = plan
  variables { node_scaling = { min = 2, max = 3, desired = 4 } }
  expect_failures = [var.node_scaling]
}
