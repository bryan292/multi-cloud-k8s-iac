variable "workload_identities" {
  description = "Application identities with explicit resource-scoped roles."
  type = map(object({
    namespace       = string
    service_account = string
    permissions = object({
      role_assignments = list(object({ scope = string, role_definition_id = string }))
    })
  }))
  default = {}
  validation {
    condition = alltrue([for key, identity in var.workload_identities :
      can(regex("^[a-z][a-z0-9-]{0,23}$", key)) &&
      can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", identity.namespace)) &&
      can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", identity.service_account))
    ]) && length(distinct([for identity in var.workload_identities : "${identity.namespace}/${identity.service_account}"])) == length(var.workload_identities)
    error_message = "Use valid DNS labels and unique namespace/service account subjects."
  }
  validation {
    condition = alltrue([for identity in var.workload_identities :
      length(identity.permissions.role_assignments) > 0 && alltrue([for assignment in identity.permissions.role_assignments :
        can(regex("(?i)^/subscriptions/${var.subscription_id}/resourceGroups/[^/*?]+(/providers/[^*?]+)?$", assignment.scope)) &&
        can(regex("(?i)^/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/[0-9a-f-]{36}$", assignment.role_definition_id)) &&
        !contains(["8e3af657-a8ff-443c-a75c-2fe8c4bcb635", "b24988ac-6180-42a0-ab88-20f7382dd24c", "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9", "f1a07417-d97a-45cb-824c-7a7467783830"], lower(element(reverse(split("/", assignment.role_definition_id)), 0)))
      ])
    ])
    error_message = "Use resource/group scopes and explicit non-administrative role IDs in the configured subscription."
  }
}

locals {
  workload_role_assignments = merge({}, [for key, identity in var.workload_identities : {
    for assignment in identity.permissions.role_assignments : "${key}-${sha256(lower("${assignment.scope}|${assignment.role_definition_id}"))}" => merge(assignment, { identity_key = key })
  }]...)
}

resource "azurerm_user_assigned_identity" "workload" {
  for_each            = var.workload_identities
  name                = "${local.name}-wi-${each.key}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "workload" {
  for_each  = var.workload_identities
  name      = "kubernetes-service-account"
  parent_id = azurerm_user_assigned_identity.workload[each.key].id
  audience  = ["api://AzureADTokenExchange"]
  issuer    = azurerm_kubernetes_cluster.this.oidc_issuer_url
  subject   = "system:serviceaccount:${each.value.namespace}:${each.value.service_account}"
}

resource "azurerm_role_assignment" "workload" {
  for_each                         = local.workload_role_assignments
  scope                            = each.value.scope
  role_definition_id               = each.value.role_definition_id
  principal_id                     = azurerm_user_assigned_identity.workload[each.value.identity_key].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

output "workload_identity_bindings" {
  description = "GitOps ServiceAccounts and pod labels; contains identifiers only, never credentials."
  value = { for key, identity in var.workload_identities : key => {
    provider = "azure"
    audience = "api://AzureADTokenExchange"
    subject  = "system:serviceaccount:${identity.namespace}:${identity.service_account}"
    service_account = {
      apiVersion = "v1"
      kind       = "ServiceAccount"
      metadata = {
        name      = identity.service_account
        namespace = identity.namespace
        annotations = {
          "azure.workload.identity/client-id" = azurerm_user_assigned_identity.workload[key].client_id
          "azure.workload.identity/tenant-id" = var.tenant_id
        }
      }
      automountServiceAccountToken = false
    }
    pod_labels = { "azure.workload.identity/use" = "true" }
  } }
}
