variable "workload_identities" {
  description = "Application identities; existing controller IRSA roles are managed separately."
  type = map(object({
    namespace       = string
    service_account = string
    permissions = object({
      statements = list(object({ actions = list(string), resources = list(string) }))
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
      length(identity.permissions.statements) > 0 && alltrue([for statement in identity.permissions.statements :
        length(statement.actions) > 0 && length(statement.resources) > 0 &&
        alltrue([for action in statement.actions : can(regex("^[a-z0-9-]+:[A-Za-z][A-Za-z0-9]+$", action)) && !contains(["iam", "sts", "organizations", "account"], split(":", action)[0])]) &&
        alltrue([for resource in statement.resources : can(regex("^arn:aws[a-z-]*:[a-z0-9-]+:[^*?]*:[^*?]*:[^*?]+$", resource))])
      ])
    ])
    error_message = "Specify concrete actions and resource ARNs without wildcards or identity/account administration."
  }
}

resource "aws_iam_role" "workload" {
  for_each = var.workload_identities
  name     = "${substr("${var.environment}-${var.cluster_name}", 0, 24)}-wi-${each.key}-${substr(sha256("${var.environment}/${var.cluster_name}"), 0, 8)}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = module.eks.oidc_provider_arn }
      Condition = {
        StringEquals = {
          "${module.eks.oidc_provider}:aud" = "sts.amazonaws.com"
          "${module.eks.oidc_provider}:sub" = "system:serviceaccount:${each.value.namespace}:${each.value.service_account}"
        }
      }
    }]
  })
  max_session_duration = 3600
  tags                 = var.tags
}

resource "aws_iam_role_policy" "workload" {
  for_each = var.workload_identities
  name     = "workload-scoped-access"
  role     = aws_iam_role.workload[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [for statement in each.value.permissions.statements : {
      Effect   = "Allow"
      Action   = statement.actions
      Resource = statement.resources
    }]
  })
}

output "workload_identity_bindings" {
  description = "GitOps ServiceAccounts and pod labels; contains identifiers only, never credentials."
  value = { for key, identity in var.workload_identities : key => {
    provider = "aws"
    audience = "sts.amazonaws.com"
    subject  = "system:serviceaccount:${identity.namespace}:${identity.service_account}"
    service_account = {
      apiVersion = "v1"
      kind       = "ServiceAccount"
      metadata = {
        name        = identity.service_account
        namespace   = identity.namespace
        annotations = { "eks.amazonaws.com/role-arn" = aws_iam_role.workload[key].arn }
      }
      automountServiceAccountToken = false
    }
    pod_labels = tomap({})
  } }
}
