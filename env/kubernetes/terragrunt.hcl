terraform {
  source = "../../initial-infra/kubernetes"
}

dependency "network" {
  config_path = "../aws/network"
}


dependency "eks" {
  config_path = "../aws/eks"
}

include "global" {
  path   = find_in_parent_folders()
  expose = true
}

inputs = {
  region          = include.global.locals.config.global.region
  host            = dependency.eks.outputs.eks_cluster_endpoint
  cluster_ca_cert = dependency.eks.outputs.eks_cluster_certificate_authority_data
  cluster_name    = dependency.eks.outputs.eks_cluster_name
}