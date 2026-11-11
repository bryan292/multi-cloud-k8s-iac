mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  }
}
variables {
  vpc_name     = "test-vpc"
  cluster_name = "test-cluster"
  environment  = "test"
  account_id   = "123456789012"
  region       = "us-east-1"
  vpc_cidr     = "10.42.0.0/16"
}
run "custom_network" {
  command = plan
  assert {
    condition     = module.network.vpc_cidr_block == "10.42.0.0/16" && module.network.private_subnets_cidr_blocks == tolist(["10.42.1.0/24", "10.42.2.0/24", "10.42.3.0/24"])
    error_message = "Configured CIDR must propagate to VPC and private subnets."
  }
}
run "reject_single_az" {
  command = plan
  variables { az_count = 1 }
  expect_failures = [var.az_count]
}
