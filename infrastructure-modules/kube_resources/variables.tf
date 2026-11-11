variable "region" {
  type = string
}

variable "aws_profile" {
  description = "AWS CLI profile used by the Kubernetes provider exec credential plugin."
  type        = string
}

variable "host" {
  type = string
}

variable "cluster_ca_cert" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "kubeconfig_path" {
  type    = string
  default = null
}

variable "platform" {
  description = "Immutable Git source containing the Flux platform configuration."
  type = object({
    repository  = string
    commit      = string
    secret_name = optional(string, "")
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
