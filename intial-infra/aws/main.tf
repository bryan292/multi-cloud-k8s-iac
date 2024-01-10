terraform {
  backend "s3" {
    bucket         = "multi-cloud-k8s-iac"
    key            = "terraform.tfstate"
    region         = "us-east-1" # Replace with your desired AWS region
    # encrypt        = true
    # dynamodb_table = "terraform-lock" # Optional: Use DynamoDB for locking
  }
}

locals {
  name = "demo"
  tags = merge(
    var.common_tags,
    {
      DeploymentDate = "timestamp"
    }
  )
}

# Include the VPC module for network setup
module "network" {
  source = "./network"  # Update with the actual path to your vpc/ module
  vpc_cidr           = "10.0.0.0/16"  # Specify the CIDR block for the VPC
  vpc_name           = "${local.name}-vpc"      # Customize the name for the VPC
  cluster_name       = "${local.name}-cluster"
  tags = local.tags
  domain = "292s.io"
  # Add more variables as needed for your project
}

# Include the EKS module for cluster setup
module "eks_cluster" {
  source = "./eks"  # Update with the actual path to your eks/ module
  cluster_name = "${local.name}-cluster"  # Customize with your desired cluster name
  subnet_ids   = module.network.private_subnets_ids
  control_plane_subnet_ids = module.network.intra_subnets_ids
  vpc_id = module.network.vpc_id
  tags = local.tags
  region = var.aws_region  
}

module "argocd" {
  source = "../modules/argocd/infra"
  region = var.aws_region
  host = module.eks_cluster.eks_cluster_endpoint
  cluster_ca_cert = module.eks_cluster.eks_cluster_certificate_authority_data
  cluster_name = module.eks_cluster.eks_cluster_name
}