variable "environment" {
  type = string
}

variable "kubeconfig_path" {
  type = string
}

variable "provider_name" {
  type = string
  validation {
    condition     = contains(["aws", "azure"], var.provider_name)
    error_message = "provider_name must be aws or azure."
  }
}

variable "cluster_settings" {
  description = "Non-secret values injected into Flux substitutions."
  type        = map(string)
}

variable "platform" {
  description = "Immutable Git source containing the Flux platform configuration."
  type = object({
    repository  = string
    commit      = string
    secret_name = optional(string, "")
    path        = string
  })
}

variable "application" {
  type    = object({ enabled = optional(bool, false), repository = optional(string, ""), commit = optional(string, ""), path = optional(string, "./"), secret_name = optional(string, "") })
  default = {}
}

variable "create_storage_class" {
  type    = bool
  default = true
}
