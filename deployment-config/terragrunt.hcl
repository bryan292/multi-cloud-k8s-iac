locals {
  config = yamldecode(file("${get_repo_root()}/config.yaml"))
  global = try(local.config.global, {})
  aws    = try(local.config.aws, {})
  azure  = try(local.config.azure, {})
  kubernetes_version = try(local.global.kubernetes_version, null)
  provider = try(local.global.provider, "aws")
}

# Provider-specific logic for inputs and remote state
inputs = local.provider == "aws" ? {
  kubernetes_version = local.kubernetes_version
  # Add other AWS-specific inputs here if needed
} : local.provider == "azure" ? {
  kubernetes_version     = local.kubernetes_version
  resource_group_name    = local.azure.resource_group_name
  location               = local.azure.location
  aks_name               = local.global.cluster_name
  node_count             = local.azure.node_count
  node_vm_size           = local.azure.node_vm_size
  dns_prefix             = local.azure.dns_prefix
  # Add other Azure-specific inputs here if needed
} : {}

remote_state {
  backend = local.provider == "aws" ? "s3" : "azurerm"
  generate = {
    path      = "state.tf"
    if_exists = "overwrite"
  }
  config = local.provider == "aws" ? {
    bucket         = local.aws.bucket_name
    key            = "~${local.global.cluster_name}/${local.global.environment}/${path_relative_to_include()}/terraform.tfstate"
    region         = local.aws.region
    dynamodb_table = "${local.global.environment}-${local.global.cluster_name}"
  } : {
    resource_group_name  = local.azure.resource_group_name
    storage_account_name = "tfstate${replace(local.azure.resource_group_name, "-", "")}"
    container_name       = "tfstate"
    key                  = "${local.global.cluster_name}.terraform.tfstate"
    use_azuread_auth     = false
    # Ensure the resource group exists before using the backend
  }
}
