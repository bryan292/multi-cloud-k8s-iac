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
