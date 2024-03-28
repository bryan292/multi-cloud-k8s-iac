
# Filter out local zones, which are not currently supported 
# with managed node groups
data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

module "network" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.4.0"

  name = "${var.environment}-${var.vpc_name}"
  #TODO: Add bellow as variables to the module definition:
  cidr = "10.0.0.0/16"

  azs = slice(data.aws_availability_zones.available.names, 0, 3)

  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.4.0/24", "10.0.5.0/24", "10.0.6.0/24"]
  intra_subnets   = ["10.0.7.0/24", "10.0.8.0/24", "10.0.9.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true

  public_subnet_tags = {
    "kubernetes.io/cluster/${var.environment}-${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                                       = 1
  }

  private_subnet_tags = {
    "kubernetes.io/cluster/${var.environment}-${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"                              = 1
  }
  tags = var.tags
}
