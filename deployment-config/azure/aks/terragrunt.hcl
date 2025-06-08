
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
  resource_group_name = include.global.locals.config.azure.resource_group_name
  location            = include.global.locals.config.azure.location
  aks_name            = include.global.locals.config.azure.aks_name
  node_count          = include.global.locals.config.azure.node_count
  node_vm_size        = include.global.locals.config.azure.node_vm_size
  dns_prefix          = include.global.locals.config.azure.dns_prefix
  kubernetes_version  = include.global.locals.config.global.kubernetes_version
  client_id           = include.global.locals.config.azure.client_id
  client_secret       = include.global.locals.config.azure.client_secret
  subscription_id     = include.global.locals.config.azure.subscription_id
  tenant_id           = include.global.locals.config.azure.tenant_id
  tags                = include.global.locals.config.global.common_tags
} : {}
