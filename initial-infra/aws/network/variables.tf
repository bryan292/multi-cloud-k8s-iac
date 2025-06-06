
variable "vpc_name" {
  description = "Name for the VPC."
  type        = string
}

variable "cluster_name" {
  description = "Name for the cluster."
  type        = string
}

variable "domain" {
  description = "Name for the domain."
  type        = string
}
variable "tags" {
  description = "List of tags for the module."
  type        = map(string)
}

variable "environment" {
  description = "The environment where the resources will be deployed."
  type        = string
}
