provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
  client_id       = var.client_id
  client_secret   = var.client_secret
}

# Use the provided resource group for all resources
locals {
  aks_resource_group_name = var.resource_group_name
  aks_resource_group_location = var.location
}

resource "azurerm_kubernetes_cluster" "aks" {
  name                = "${var.environment}-${var.aks_name}"
  location            = local.aks_resource_group_location
  resource_group_name = local.aks_resource_group_name
  dns_prefix          = var.dns_prefix

  default_node_pool {
    name       = "default"
    node_count = var.node_count
    vm_size    = var.node_vm_size
  }

  identity {
    type = "SystemAssigned"
  }

  kubernetes_version = var.kubernetes_version

  tags = var.tags
}

resource "local_file" "kubeconfig" {
  filename = "${var.terragrunt_dir}/../../../kubeconfig.yaml"
  content = templatefile("${var.terragrunt_dir}/../../../infrastructure-modules/azure/kubeconfig/kubeconfig.tpl", {
    endpoint                   = azurerm_kubernetes_cluster.aks.kube_config[0].host
    certificate_authority_data = azurerm_kubernetes_cluster.aks.kube_config[0].cluster_ca_certificate
    client_certificate         = azurerm_kubernetes_cluster.aks.kube_config[0].client_certificate
    client_key                 = azurerm_kubernetes_cluster.aks.kube_config[0].client_key
    cluster_name               = azurerm_kubernetes_cluster.aks.name
  })
}

