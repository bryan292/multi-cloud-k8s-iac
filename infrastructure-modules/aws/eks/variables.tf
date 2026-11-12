variable "cluster_name" {
  description = "The name for your EKS cluster."
  type        = string
}

variable "vpc_id" {
  description = "The ID of the created VPC."
  type        = string
}


variable "subnet_ids" {
  description = "A list of subnet IDs where the EKS cluster will be deployed."
  type        = list(string)
}

variable "control_plane_subnet_ids" {
  description = "A list of subnet IDs where the EKS cluster will be deployed."
  type        = list(string)
}

variable "tags" {
  description = "List of tags for the module."
  type        = map(string)
}

variable "region" {
  description = "Cluster Region."
  type        = string
}

variable "terragrunt_dir" {
  description = "The directory where the Terragrunt configuration is located."
  type        = string

}

variable "environment" {
  description = "The environment where the resources will be deployed."
  type        = string

}

variable "cluster_autoscaler" {
  type        = bool
  description = "value to enable or disable cluster autoscaler"
  default     = false
}

variable "kubernetes_version" {
  description = "The version of Kubernetes to use for the EKS cluster."
  type        = string
}
variable "account_id" {
  type = string
}

variable "aws_profile" {
  description = "Local AWS CLI profile embedded in the generated kubeconfig exec environment."
  type        = string

  validation {
    condition     = length(trimspace(var.aws_profile)) > 0
    error_message = "aws_profile cannot be empty."
  }
}

variable "hosted_zone_id" {
  type = string
}

variable "admin_cidrs" {
  type    = list(string)
  default = []
  validation {
    condition     = alltrue([for cidr in var.admin_cidrs : can(cidrnetmask(cidr)) && !endswith(cidr, "/0")])
    error_message = "Admin CIDRs must be valid IPv4 ranges and cannot allow the whole Internet."
  }
}

variable "admin_principal_arns" {
  type = list(string)
  validation {
    condition     = length(var.admin_principal_arns) > 0 && alltrue([for arn in var.admin_principal_arns : can(regex("^arn:[^:]+:iam::[0-9]{12}:(role|user)/.+", arn))])
    error_message = "Provide at least one permanent IAM role or user ARN, including the deployment role."
  }
}

variable "node_instance_types" {
  type    = list(string)
  default = ["m6i.large", "m6a.large", "m5.large"]
}

variable "node_capacity_type" {
  type    = string
  default = "ON_DEMAND"
  validation {
    condition     = contains(["ON_DEMAND", "SPOT"], var.node_capacity_type)
    error_message = "Use ON_DEMAND or SPOT."
  }
}

variable "node_scaling" {
  type    = object({ min = number, max = number, desired = number })
  default = { min = 2, max = 6, desired = 2 }
  validation {
    condition     = var.node_scaling.min >= 2 && var.node_scaling.min <= var.node_scaling.desired && var.node_scaling.desired <= var.node_scaling.max
    error_message = "Require 2 <= min <= desired <= max."
  }
}

variable "addon_versions" {
  type    = object({ coredns = optional(string), kube_proxy = optional(string), vpc_cni = optional(string), ebs_csi = optional(string) })
  default = {}
}

variable "kubeconfig_path" {
  description = "Optional explicit kubeconfig path for isolated operational targets."
  type        = string
  default     = null
}
