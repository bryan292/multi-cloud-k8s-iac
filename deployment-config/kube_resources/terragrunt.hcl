terraform { source = "../../infrastructure-modules/kube_resources" }
dependency "cluster" {
  config_path = include.global.locals.provider == "aws" ? "../aws/eks" : "../azure/aks"
}
dependency "kubernetes" {
  config_path  = "../kubernetes"
  skip_outputs = true
}
include "global" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}
inputs = {
  kubeconfig_path = "${get_repo_root()}/kubeconfig.yaml"
  environment     = include.global.locals.config.global.environment
  provider_name   = include.global.locals.provider
  platform = merge(include.global.locals.config.platform, {
    path = include.global.locals.config.platform.path != "" ? include.global.locals.config.platform.path : "./clusters/${include.global.locals.config.global.environment}/${include.global.locals.provider}"
  })
  application          = include.global.locals.config.application
  create_storage_class = include.global.locals.provider == "aws"
  cluster_settings = merge(
    {
      provider           = include.global.locals.provider
      cluster_name       = dependency.cluster.outputs.cluster_name
      kubernetes_version = include.global.locals.config.global.kubernetes_version
      storage_class      = include.global.locals.provider == "aws" ? "gp3" : "managed-csi"
    },
    include.global.locals.provider == "aws" ? {
      region                      = include.global.locals.config.aws.region
      vpc_id                      = dependency.cluster.outputs.vpc_id
      domain                      = include.global.locals.config.network.domain
      hosted_zone_id              = include.global.locals.config.network.hosted_zone_id
      acme_email                  = include.global.locals.config.platform.acme_email
      eks_lb_role_arn             = dependency.cluster.outputs.eks_lb_role_arn
      eks_cm_role_arn             = dependency.cluster.outputs.eks_cm_role_arn
      eks_external_dns_role_arn   = dependency.cluster.outputs.eks_external_dns_role_arn
      cluster_autoscaler_role_arn = dependency.cluster.outputs.cluster_autoscaler_role_arn
      } : {
      region = include.global.locals.config.azure.location
    }
  )
}
