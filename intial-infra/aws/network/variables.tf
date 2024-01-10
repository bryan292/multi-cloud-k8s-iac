variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
}

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


# variable "subnet_cidr_blocks" {
#   description = "List of CIDR blocks for subnets within the VPC."
#   type        = list(string)
# }

# variable "availability_zones" {
#   description = "List of availability zones for subnets."
#   type        = list(string)
# }
