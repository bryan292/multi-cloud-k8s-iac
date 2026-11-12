locals {
  config   = yamldecode(file(get_env("IAC_CONFIG", "${get_repo_root()}/config.yaml")))
  provider = local.config.global.provider
}
remote_state {
  backend  = local.provider == "aws" ? "s3" : "azurerm"
  generate = { path = "state.tf", if_exists = "overwrite_terragrunt" }
  config = jsondecode(local.provider == "aws" ? jsonencode({
    bucket              = local.config.aws.bucket_name
    key                 = "~${local.config.global.cluster_name}/${local.config.global.environment}/${path_relative_to_include()}/terraform.tfstate"
    region              = local.config.aws.state_region
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = [local.config.aws.account_id]
    }) : jsonencode({
    resource_group_name  = local.config.azure.state.resource_group_name
    storage_account_name = local.config.azure.state.storage_account_name
    container_name       = local.config.azure.state.container_name
    key                  = "${local.config.global.cluster_name}/${local.config.global.environment}/${path_relative_to_include()}/terraform.tfstate"
    use_azuread_auth     = true
    subscription_id      = local.config.azure.subscription_id
    tenant_id            = local.config.azure.tenant_id
  }))
}
