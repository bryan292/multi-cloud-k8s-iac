mock_provider "azurerm" {}
mock_provider "local" {}

variables {
  subscription_id                 = "00000000-0000-0000-0000-000000000000"
  tenant_id                       = "11111111-1111-1111-1111-111111111111"
  location                        = "eastus"
  resource_group_name             = "test-aks"
  cluster_name                    = "test"
  kubernetes_version              = "1.35"
  environment                     = "dev"
  vnet_cidr                       = "10.70.0.0/16"
  subnet_cidr                     = "10.70.0.0/20"
  api_server_authorized_ip_ranges = ["203.0.113.10/32"]
  node_pool = {
    vm_size = "Standard_D2s_v3"
    zones   = ["1", "2"]
    min     = 2
    desired = 2
    max     = 4
  }
  kubeconfig_path = "/tmp/aks-test-kubeconfig"
}

run "secure_plan" {
  command = plan

  assert {
    condition     = azurerm_kubernetes_cluster.this.local_account_disabled
    error_message = "Local AKS accounts must remain disabled."
  }

  assert {
    condition     = azurerm_kubernetes_cluster.this.workload_identity_enabled && azurerm_kubernetes_cluster.this.oidc_issuer_enabled
    error_message = "AKS workload identity and OIDC must remain enabled."
  }

  assert {
    condition     = azurerm_kubernetes_cluster.this.network_profile[0].network_data_plane == "cilium"
    error_message = "AKS must use the Cilium data plane."
  }
}

run "reject_public_internet" {
  command = plan
  variables {
    api_server_authorized_ip_ranges = ["0.0.0.0/0"]
  }
  expect_failures = [var.api_server_authorized_ip_ranges]
}
