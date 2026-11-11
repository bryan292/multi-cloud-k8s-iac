provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags { tags = var.tags }
}
data "aws_availability_zones" "available" {
  state = "available"
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}
module "network" {
  source                                          = "terraform-aws-modules/vpc/aws"
  version                                         = "5.21.0"
  name                                            = "${var.environment}-${var.vpc_name}"
  cidr                                            = var.vpc_cidr
  azs                                             = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  private_subnets                                 = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 1)]
  public_subnets                                  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 4)]
  intra_subnets                                   = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 7)]
  enable_nat_gateway                              = true
  single_nat_gateway                              = var.single_nat_gateway
  one_nat_gateway_per_az                          = !var.single_nat_gateway
  enable_dns_hostnames                            = true
  enable_dns_support                              = true
  enable_flow_log                                 = true
  create_flow_log_cloudwatch_log_group            = true
  create_flow_log_cloudwatch_iam_role             = true
  flow_log_cloudwatch_log_group_retention_in_days = 30
  public_subnet_tags                              = { "kubernetes.io/role/elb" = "1" }
  private_subnet_tags                             = { "kubernetes.io/role/internal-elb" = "1" }
  tags                                            = var.tags
}
