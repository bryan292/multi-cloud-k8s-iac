# intial-infra\aws\eks\terragrunt.hcl

dependency "eks" {
  config_path = "../aws/eks"
}

dependency "network" {
  config_path = "../aws/network"
}

include "global"{
  path = find_in_parent_folders()
  expose  = true
}

inputs = {
  region          = include.global.locals.config.global.region
  host            = dependency.eks.outputs.eks_cluster_endpoint
  cluster_ca_cert = dependency.eks.outputs.eks_cluster_certificate_authority_data
  cluster_name    = dependency.eks.outputs.eks_cluster_name
  domain          = include.global.locals.config.network.domain
  hosted_zone_id  = include.global.locals.config.network.hosted_zone_id
  vpc_id          = dependency.network.outputs.vpc_id
  eks_lb_role_arn = dependency.eks.outputs.eks_lb_role_arn
  eks_cm_role_arn = dependency.eks.outputs.eks_cm_role_arn
  eks_external_dns_role_arn = dependency.eks.outputs.eks_external_dns_role_arn
}