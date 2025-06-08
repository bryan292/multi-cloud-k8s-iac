variable "resource_group_name" {
  description = "The name of the resource group in which to create the AKS cluster."
  type        = string
}

variable "location" {
  description = "The Azure location where the resources will be created."
  type        = string
}

variable "aks_name" {
  description = "The name of the AKS cluster."
  type        = string
}

variable "node_count" {
  description = "The number of nodes in the default node pool."
  type        = number
  default     = 2
}

variable "node_vm_size" {
  description = "The size of the VMs in the default node pool."
  type        = string
  default     = "Standard_DS2_v2"
}

variable "dns_prefix" {
  description = "DNS prefix for the AKS cluster."
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for the AKS cluster."
  type        = string
}

variable "client_id" {
  description = "Azure service principal client ID."
  type        = string
}

variable "client_secret" {
  description = "Azure service principal client secret."
  type        = string
  sensitive   = true
}

variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "tenant_id" {
  description = "Azure tenant ID."
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources."
  type        = map(string)
  default     = {}
}

variable "terragrunt_dir" {
  description = "The directory where the Terragrunt configuration is located."
  type        = string

}

variable "environment" {
  description = "The environment where the resources will be deployed."
  type        = string

}