terraform {
  source = "../../initial-infra/kube_resources"
}

dependency "network" {
  config_path = "../aws/network"
}


dependency "eks" {
  config_path = "../aws/eks"
}

dependency "kubernetes" {
  config_path  = "../kubernetes"
  skip_outputs = true
}

include "global" {
  path   = find_in_parent_folders()
  expose = true
}

inputs = {
  region                      = include.global.locals.config.global.region
  host                        = dependency.eks.outputs.eks_cluster_endpoint
  cluster_ca_cert             = dependency.eks.outputs.eks_cluster_certificate_authority_data
  environment                 = include.global.locals.config.global.environment
  cluster_name                = dependency.eks.outputs.eks_cluster_name
  domain                      = include.global.locals.config.network.domain
  hosted_zone_id              = include.global.locals.config.network.hosted_zone_id
  vpc_id                      = dependency.network.outputs.vpc_id
  eks_lb_role_arn             = dependency.eks.outputs.eks_lb_role_arn
  eks_cm_role_arn             = dependency.eks.outputs.eks_cm_role_arn
  eks_external_dns_role_arn   = dependency.eks.outputs.eks_external_dns_role_arn
  cluster_autoscaler_role_arn = dependency.eks.outputs.cluster_autoscaler_role_arn
  cluster_autoscaler          = include.global.locals.config.umbrella.cluster_autoscaler
  repository                  = include.global.locals.config.global.app_repo
  app_name                    = include.global.locals.config.global.app_name
  branch                      = include.global.locals.config.global.branch
  email                       = include.global.locals.config.global.email
  external_dns = include.global.locals.config.umbrella.external_dns
  metrics_server = include.global.locals.config.umbrella.metrics_server
  cert_manager = include.global.locals.config.umbrella.cert_manager
  prometheus = include.global.locals.config.umbrella.prometheus
  grafana =   include.global.locals.config.umbrella.grafana
  loki = include.global.locals.config.umbrella.loki
  aws_load_balancer_controller = include.global.locals.config.umbrella.aws_load_balancer_controller
  weave_gitops = include.global.locals.config.umbrella.weave_gitops
  custom_app = include.global.locals.config.umbrella.custom_app

}