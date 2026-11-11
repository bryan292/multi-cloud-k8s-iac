terraform { source = "../../../infrastructure-modules/aws/eks" }
dependency "network" { config_path = "../network" }
include "global" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}
inputs = {
  terragrunt_dir           = get_terragrunt_dir()
  cluster_name             = "${include.global.locals.config.global.cluster_name}-cluster"
  environment              = include.global.locals.config.global.environment
  tags                     = include.global.locals.config.global.common_tags
  region                   = include.global.locals.config.aws.region
  account_id               = include.global.locals.config.aws.account_id
  aws_profile              = include.global.locals.config.aws.profile
  kubernetes_version       = include.global.locals.config.global.kubernetes_version
  subnet_ids               = dependency.network.outputs.private_subnets_ids
  control_plane_subnet_ids = dependency.network.outputs.intra_subnets_ids
  vpc_id                   = dependency.network.outputs.vpc_id
  hosted_zone_id           = include.global.locals.config.network.hosted_zone_id
  cluster_autoscaler       = include.global.locals.config.umbrella.cluster_autoscaler
  admin_cidrs              = include.global.locals.config.eks.admin_cidrs
  admin_principal_arns     = include.global.locals.config.eks.admin_principal_arns
  node_instance_types      = include.global.locals.config.eks.node_instance_types
  node_capacity_type       = include.global.locals.config.eks.node_capacity_type
  node_scaling             = include.global.locals.config.eks.node_scaling
  addon_versions           = include.global.locals.config.eks.addon_versions
}
