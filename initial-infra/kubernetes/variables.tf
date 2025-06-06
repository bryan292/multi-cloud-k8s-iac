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
