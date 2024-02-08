# intial-infra\aws\network\terragrunt.hcl

include "global"{
  path = find_in_parent_folders()
  expose  = true
}

inputs = {
  vpc_cidr     = "${include.global.locals.config.network.vpc_cidr}"       # Specify the CIDR block for the VPC
  vpc_name     = "${include.global.locals.config.global.cluster_name}-vpc" # Customize the name for the VPC
  cluster_name = "${include.global.locals.config.global.cluster_name}-cluster"
  tags         = include.global.locals.config.global.common_tags
  domain       = include.global.locals.config.network.domain
  # Add more variables as needed for your project
}
