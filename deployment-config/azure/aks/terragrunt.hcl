terraform { source = "../../../infrastructure-modules/azure/aks" }

include "global" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

inputs = {
  subscription_id                 = include.global.locals.config.azure.subscription_id
  tenant_id                       = include.global.locals.config.azure.tenant_id
  location                        = include.global.locals.config.azure.location
  resource_group_name             = include.global.locals.config.azure.resource_group_name
  cluster_name                    = include.global.locals.config.global.cluster_name
  kubernetes_version              = include.global.locals.config.global.kubernetes_version
  environment                     = include.global.locals.config.global.environment
  tags                            = include.global.locals.config.global.common_tags
  vnet_cidr                       = include.global.locals.config.azure.network.vnet_cidr
  subnet_cidr                     = include.global.locals.config.azure.network.subnet_cidr
  api_server_authorized_ip_ranges = include.global.locals.config.azure.network.api_server_authorized_ip_ranges
  node_pool                       = include.global.locals.config.azure.node_pool
  kubeconfig_path                 = "${get_repo_root()}/kubeconfig.yaml"
}
