variable "region" {
  description = "Cluster Region."
  type        = string
}

variable "host" {
  description = "The endpoint of the EKS cluster."
  type        = string
}

variable "cluster_ca_cert" {
  description = "Base64 encoded certificate data required to communicate with the cluster."
  type        = string
}

variable "cluster_name" {
  description = "The name of the EKS cluster."
  type        = string
}

variable "domain" {
  description = "Name for the domain."
  type        = string
}

variable "vpc_id" {
  description = "The ID of the created VPC."
  type        = string
}

variable "eks_lb_role_arn" {
  description = "The lb role arn."
  type        = string
}

variable "eks_cm_role_arn" {
  description = "The cm role arn."
  type        = string
}

variable "eks_external_dns_role_arn" {
  description = "The external-dns role arn."
  type        = string
}

variable "cluster_autoscaler_role_arn" {
  description = "The cluster auto scaler role arn."
  type        = string

}

variable "hosted_zone_id" {
  description = "Hosted Zone Id for the configured domain."
  type        = string
}

variable "environment" {
  description = "The environment where the resources will be deployed."
  type        = string

}

variable "repository" {
  description = "The repository where the resources are stored."
  type        = string
}

variable "branch" {
  description = "The branch of the repository."
  type        = string
}

variable "app_name" {
  description = "The name of the application."
  type        = string

}
