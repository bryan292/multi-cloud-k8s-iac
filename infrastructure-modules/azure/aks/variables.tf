variable "subscription_id" {
  type = string
}

variable "tenant_id" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "kubernetes_version" {
  type = string
}

variable "environment" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "vnet_cidr" {
  type = string
}

variable "subnet_cidr" {
  type = string
}

variable "api_server_authorized_ip_ranges" {
  type    = list(string)
  default = []
  validation {
    condition = alltrue([
      for cidr in var.api_server_authorized_ip_ranges :
      can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"
    ])
    error_message = "AKS API ranges must be valid and cannot allow the entire internet."
  }
}

variable "node_pool" {
  type = object({
    vm_size = string
    zones   = list(string)
    min     = number
    desired = number
    max     = number
  })
  validation {
    condition     = var.node_pool.min >= 2 && var.node_pool.min <= var.node_pool.desired && var.node_pool.desired <= var.node_pool.max
    error_message = "Require 2 <= min <= desired <= max for the AKS system pool."
  }
}

variable "kubeconfig_path" {
  type = string
}
