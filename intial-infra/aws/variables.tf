variable "aws_region" {
  description = "The AWS region where the resources will be created."
  default     = "us-east-1"  # Replace with your desired AWS region
}

variable "common_tags" {
  description = "Common tags to apply to resources"
  type        = map(string)
  default     = {
    Environment = "Production",
    Owner       = "Bryan Cerdas",
    project     = "Multi-Cloud-K8s"
  }
}


# variable "cluster_name" {
#   description = "The name for your EKS cluster."
#   type        = string
# }

# variable "node_group" {
#   description = "The configuration for your EKS node group."
#   type        = map(string)
# }

# variable "vpc_name" {
#   description = "The name for your VPC."
#   type        = string
#   default     = "my-vpc"  # Replace with your VPC name
# }

# Add more variables as needed for your project
