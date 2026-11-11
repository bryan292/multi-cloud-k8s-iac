provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

data "azurerm_client_config" "current" {}

locals {
  name            = "${var.environment}-${var.cluster_name}-cluster"
  private_cluster = length(var.api_server_authorized_ip_ranges) == 0
}

resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_virtual_network" "this" {
  name                = "${local.name}-vnet"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = [var.vnet_cidr]
  tags                = var.tags
}

resource "azurerm_subnet" "nodes" {
  name                            = "aks-nodes"
  resource_group_name             = azurerm_resource_group.this.name
  virtual_network_name            = azurerm_virtual_network.this.name
  address_prefixes                = [var.subnet_cidr]
  default_outbound_access_enabled = false
}

resource "azurerm_log_analytics_workspace" "this" {
  name                         = "${local.name}-logs"
  location                     = azurerm_resource_group.this.location
  resource_group_name          = azurerm_resource_group.this.name
  sku                          = "PerGB2018"
  retention_in_days            = 30
  daily_quota_gb               = 1
  local_authentication_enabled = false
  tags                         = var.tags
}

resource "azurerm_kubernetes_cluster" "this" {
  name                = local.name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  dns_prefix          = replace(local.name, "-", "")
  kubernetes_version  = var.kubernetes_version
  sku_tier            = "Free"

  local_account_disabled            = true
  oidc_issuer_enabled               = true
  workload_identity_enabled         = true
  private_cluster_enabled           = local.private_cluster
  role_based_access_control_enabled = true
  azure_policy_enabled              = true
  run_command_enabled               = false

  automatic_upgrade_channel = "patch"
  node_os_upgrade_channel   = "NodeImage"

  dynamic "api_server_access_profile" {
    for_each = local.private_cluster ? [] : [1]
    content {
      authorized_ip_ranges = var.api_server_authorized_ip_ranges
    }
  }

  default_node_pool {
    name                 = "system"
    vm_size              = var.node_pool.vm_size
    vnet_subnet_id       = azurerm_subnet.nodes.id
    zones                = var.node_pool.zones
    auto_scaling_enabled = true
    min_count            = var.node_pool.min
    node_count           = var.node_pool.desired
    max_count            = var.node_pool.max
    max_pods             = 50
    os_disk_size_gb      = 64
    os_disk_type         = "Managed"
    type                 = "VirtualMachineScaleSets"
    upgrade_settings {
      max_surge = "33%"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  azure_active_directory_role_based_access_control {
    tenant_id          = var.tenant_id
    azure_rbac_enabled = true
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    network_policy      = "cilium"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
    pod_cidr            = "10.72.0.0/16"
    service_cidr        = "10.71.0.0/16"
    dns_service_ip      = "10.71.0.10"
  }

  oms_agent {
    log_analytics_workspace_id      = azurerm_log_analytics_workspace.this.id
    msi_auth_for_monitoring_enabled = true
  }

  maintenance_window_auto_upgrade {
    frequency   = "Weekly"
    interval    = 1
    duration    = 4
    day_of_week = "Sunday"
    start_time  = "03:00"
    utc_offset  = "+00:00"
  }

  maintenance_window_node_os {
    frequency   = "Weekly"
    interval    = 1
    duration    = 4
    day_of_week = "Sunday"
    start_time  = "07:00"
    utc_offset  = "+00:00"
  }

  tags = var.tags

}

resource "azurerm_role_assignment" "deployer_cluster_admin" {
  scope                = azurerm_kubernetes_cluster.this.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "local_sensitive_file" "kubeconfig" {
  filename = var.kubeconfig_path
  content = yamlencode(merge(yamldecode(azurerm_kubernetes_cluster.this.kube_config_raw), {
    users = [
      for entry in yamldecode(azurerm_kubernetes_cluster.this.kube_config_raw).users : merge(entry, {
        user = merge(entry.user, {
          exec = merge(entry.user.exec, {
            args = [for argument in entry.user.exec.args : argument == "devicecode" ? "azurecli" : argument]
          })
        })
      })
    ]
  }))
  file_permission = "0600"
}
