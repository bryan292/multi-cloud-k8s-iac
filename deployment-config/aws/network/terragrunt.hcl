terraform { source = "../../../infrastructure-modules/aws/network" }
include "global" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}
inputs = {
  vpc_name           = "${include.global.locals.config.global.cluster_name}-vpc"
  cluster_name       = "${include.global.locals.config.global.cluster_name}-cluster"
  environment        = include.global.locals.config.global.environment
  tags               = include.global.locals.config.global.common_tags
  region             = include.global.locals.config.aws.region
  account_id         = include.global.locals.config.aws.account_id
  vpc_cidr           = include.global.locals.config.network.vpc_cidr
  az_count           = include.global.locals.config.network.az_count
  single_nat_gateway = include.global.locals.config.network.single_nat_gateway
}
