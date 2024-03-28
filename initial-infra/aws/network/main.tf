
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
# resource "aws_lb" "lb" {
#   name               = "${var.cluster_name}-lb"
#   internal           = false
#   load_balancer_type = "network"
#   subnets            = module.network.public_subnets
#   tags = var.tags
# }

# # Define target groups for HTTP and HTTPS
# resource "aws_lb_target_group" "http" {
#   name     = "${var.cluster_name}-http"
#   port     = 80
#   protocol = "TCP"
#   vpc_id   = module.network.vpc_id
# }

# resource "aws_lb_target_group" "https" {
#   name     = "${var.cluster_name}-https"
#   port     = 443
#   protocol = "TCP"
#   vpc_id   = module.network.vpc_id
# }

# # Define listeners for your NLB
# resource "aws_lb_listener" "http" {
#   load_balancer_arn = aws_lb.lb.arn
#   port              = "80"
#   protocol          = "TCP"

#   default_action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.http.arn
#   }
# }

# resource "aws_lb_listener" "https" {
#   load_balancer_arn = aws_lb.lb.arn
#   port              = "443"
#   protocol          = "TCP"

#   default_action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.https.arn
#   }
# }


# resource "aws_route53_zone" "cluster_zone" {
#   name = "${var.domain}"
# }

# resource "aws_route53_record" "example" {
#   name    = "argocd-${var.cluster_name}"
#   type    = "A" # Change to "CNAME" if using CNAME
#   zone_id = aws_route53_zone.cluster_zone.id

#   alias {
#     name                   = aws_lb.lb.dns_name
#     zone_id                = aws_lb.lb.zone_id
#     evaluate_target_health = true
#   }
# }
