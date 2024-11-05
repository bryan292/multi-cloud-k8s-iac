# intial-infra\aws\network\terragrunt.hcl
terraform {
  source = "../../../initial-infra/aws/network"
}

include "global" {
  path   = find_in_parent_folders()
  expose = true
}

inputs = {
  vpc_name     = "${include.global.locals.config.global.cluster_name}-vpc" # Customize the name for the VPC
  environment  = include.global.locals.config.global.environment
  cluster_name = "${include.global.locals.config.global.cluster_name}-cluster"
  tags         = include.global.locals.config.global.common_tags
  domain       = include.global.locals.config.network.domain
  # Add more variables as needed for your project
}
