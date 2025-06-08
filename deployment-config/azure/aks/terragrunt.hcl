
locals {
  provider = try(include.global.locals.config.global.provider, "aws")
}

skip = local.provider != "azure"

terraform {
  source = "../../../infrastructure-modules/azure/aks"
}

include "global" {
  path   = find_in_parent_folders()
  expose = true
}

inputs = local.provider == "azure" ? {
  environment              = include.global.locals.config.global.environment
  terragrunt_dir           = get_terragrunt_dir()
  resource_group_name = include.global.locals.config.azure.resource_group_name
  location            = include.global.locals.config.azure.location
  aks_name            = include.global.locals.config.global.cluster_name
  node_count          = include.global.locals.config.azure.node_count
  node_vm_size        = include.global.locals.config.azure.node_vm_size
  dns_prefix          = include.global.locals.config.azure.dns_prefix
  kubernetes_version  = include.global.locals.config.global.kubernetes_version
  client_id           = get_env("ARM_CLIENT_ID")
  client_secret       = get_env("ARM_CLIENT_SECRET")
  subscription_id     = get_env("ARM_SUBSCRIPTION_ID")
  tenant_id           = get_env("ARM_TENANT_ID")
  tags                = include.global.locals.config.global.common_tags
} : { environment = null, terragrunt_dir = null, resource_group_name = null, location = null, aks_name = null, node_count = null, node_vm_size = null, dns_prefix = null, kubernetes_version = null, client_id = null, client_secret = null, subscription_id = null, tenant_id = null, tags = null }
