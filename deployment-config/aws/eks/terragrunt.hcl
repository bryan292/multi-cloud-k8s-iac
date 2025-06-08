# intial-infra\aws\eks\terragrunt.hcl

locals {
  provider = try(include.global.locals.config.global.provider, "aws")
}

skip = local.provider != "aws"

terraform {
  source = "../../../infrastructure-modules/aws/eks"
}

dependency "network" {
  config_path = "../network"
}

include "global" {
  path   = find_in_parent_folders()
  expose = true
}

inputs = local.provider == "aws" ? {
  terragrunt_dir           = get_terragrunt_dir()
  cluster_name             = "${include.global.locals.config.global.cluster_name}-cluster" # Customize with your desired cluster name
  environment              = include.global.locals.config.global.environment
  subnet_ids               = dependency.network.outputs.private_subnets_ids
  control_plane_subnet_ids = dependency.network.outputs.intra_subnets_ids
  vpc_id                   = dependency.network.outputs.vpc_id
  cluster_autoscaler       = include.global.locals.config.umbrella.cluster_autoscaler
  tags                     = include.global.locals.config.global.common_tags
  region                   = include.global.locals.config.global.region
} : {}
