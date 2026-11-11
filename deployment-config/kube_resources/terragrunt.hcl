terraform { source = "../../infrastructure-modules/kube_resources" }
dependency "eks" { config_path = "../aws/eks" }
dependency "kubernetes" {
  config_path  = "../kubernetes"
  skip_outputs = true
}
include "global" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}
inputs = {
  aws_profile     = include.global.locals.config.global.aws_profile
  region          = include.global.locals.config.global.region
  host            = dependency.eks.outputs.eks_cluster_endpoint
  cluster_ca_cert = dependency.eks.outputs.eks_cluster_certificate_authority_data
  environment     = include.global.locals.config.global.environment
  cluster_name    = dependency.eks.outputs.eks_cluster_name
  platform        = include.global.locals.config.platform
  application     = include.global.locals.config.application
}
