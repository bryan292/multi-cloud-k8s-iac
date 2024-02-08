# intial-infra\aws\eks\terragrunt.hcl

dependency "network" {
  config_path = "../network"
}


include "global"{
  path = find_in_parent_folders()
  expose  = true
}

inputs = {
  cluster_name             = "${include.global.locals.config.global.cluster_name}-cluster" # Customize with your desired cluster name
  subnet_ids               = dependency.network.outputs.private_subnets_ids
  control_plane_subnet_ids = dependency.network.outputs.intra_subnets_ids
  vpc_id                   = dependency.network.outputs.vpc_id
  tags                     = include.global.locals.config.global.common_tags
  region                   = include.global.locals.config.global.region
}