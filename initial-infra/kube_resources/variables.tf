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

variable "cluster_autoscaler" {
  type        = bool
  description = "value to enable or disable cluster autoscaler"
  default     = false
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

variable "email" {
  description = "The email address to use for the certificate."
  type        = string

}

variable "external_dns" {
  description = "Enable or disable external-dns."
  type        = bool
  default     = false
}

variable "metrics_server" {
  description = "Enable or disable metrics-server."
  type        = bool
  default     = false
}

variable "cert_manager" {
  description = "Enable or disable cert-manager."
  type        = bool
  default     = false
}

variable "prometheus" {
  description = "Enable or disable prometheus."
  type        = bool
  default     = false
}

variable "grafana" {
  description = "Enable or disable grafana."
  type        = bool
  default     = false
}

variable "loki" {
  description = "Enable or disable loki."
  type        = bool
  default     = false
}

variable "aws_load_balancer_controller" {
  description = "Enable or disable aws-load-balancer-controller."
  type        = bool
  default     = false
}

variable "weave_gitops" {
  description = "Enable or disable weave-gitops."
  type        = bool
  default     = false
}

variable "custom_app" {
  description = "Enable or disable custom-app."
  type        = bool
  default     = false
}



