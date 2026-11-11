provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags { tags = var.tags }
}
data "aws_partition" "current" {}

locals {
  node_security_group_additional_rules = {
    ingress_cluster_prometheus = {
      description                   = "Cluster API to Prometheus service proxy"
      type                          = "ingress"
      protocol                      = "tcp"
      from_port                     = 9090
      to_port                       = 9090
      source_cluster_security_group = true
    }
  }
}

module "eks" {
  source                                   = "terraform-aws-modules/eks/aws"
  version                                  = "20.37.2"
  cluster_name                             = "${var.environment}-${var.cluster_name}"
  cluster_version                          = var.kubernetes_version
  enable_cluster_creator_admin_permissions = false
  access_entries = {
    for index, arn in var.admin_principal_arns : "admin-${index}" => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn   = "arn:${data.aws_partition.current.partition}:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }
  vpc_id                                 = var.vpc_id
  subnet_ids                             = var.subnet_ids
  control_plane_subnet_ids               = var.control_plane_subnet_ids
  cluster_endpoint_private_access        = true
  cluster_endpoint_public_access         = length(var.admin_cidrs) > 0
  cluster_endpoint_public_access_cidrs   = var.admin_cidrs
  cluster_enabled_log_types              = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  cloudwatch_log_group_retention_in_days = 30
  enable_kms_key_rotation                = true
  cluster_encryption_config              = { resources = ["secrets"] }
  node_security_group_additional_rules   = local.node_security_group_additional_rules
  cluster_addons = {
    coredns    = { addon_version = var.addon_versions.coredns }
    kube-proxy = { addon_version = var.addon_versions.kube_proxy }
    vpc-cni    = { before_compute = true, addon_version = var.addon_versions.vpc_cni }
  }
  eks_managed_node_group_defaults = {
    ami_type = "AL2023_x86_64_STANDARD"
    metadata_options = {
      http_endpoint               = "enabled"
      http_tokens                 = "required"
      http_put_response_hop_limit = 1
    }
    block_device_mappings = {
      xvda = { device_name = "/dev/xvda", ebs = { volume_size = 50, volume_type = "gp3", encrypted = true, delete_on_termination = true } }
    }
  }
  eks_managed_node_groups = {
    worker_nodes = {
      name           = "${var.environment}-${var.cluster_name}-w"
      instance_types = var.node_instance_types
      capacity_type  = var.node_capacity_type
      min_size       = var.node_scaling.min
      max_size       = var.node_scaling.max
      desired_size   = var.node_scaling.desired
      update_config  = { max_unavailable = 1 }
      autoscaling_group_tags = var.cluster_autoscaler ? {
        "k8s.io/cluster-autoscaler/enabled"                                = "true"
        "k8s.io/cluster-autoscaler/${var.environment}-${var.cluster_name}" = "owned"
      } : {}
    }
  }
  tags = var.tags
}
module "irsa-ebs-csi" {
  source                        = "terraform-aws-modules/iam/aws//modules/iam-assumable-role-with-oidc"
  version                       = "5.60.0"
  create_role                   = true
  role_name                     = "AmazonEKSTFEBSCSIRole-${module.eks.cluster_name}"
  provider_url                  = module.eks.oidc_provider
  role_policy_arns              = ["arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"]
  oidc_fully_qualified_subjects = ["system:serviceaccount:kube-system:ebs-csi-controller-sa"]
  tags                          = var.tags
}
resource "aws_eks_addon" "ebs-csi" {
  # Avoid creating the controller while the cluster still has no schedulable nodes.
  depends_on                  = [module.eks, module.irsa-ebs-csi]
  cluster_name                = module.eks.cluster_name
  addon_name                  = "aws-ebs-csi-driver"
  addon_version               = var.addon_versions.ebs_csi
  service_account_role_arn    = module.irsa-ebs-csi.iam_role_arn
  resolve_conflicts_on_update = "PRESERVE"
  tags                        = var.tags
}
# Create the IAM roles for the service accounts
module "lb_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"
  tags    = var.tags

  role_name                              = "${var.environment}_${var.cluster_name}_lb"
  attach_load_balancer_controller_policy = false
  role_policy_arns                       = { controller = aws_iam_policy.load_balancer_controller.arn }

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }
}

module "cm_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"
  tags    = var.tags

  role_name                     = "${var.environment}_${var.cluster_name}_cm"
  attach_cert_manager_policy    = true
  cert_manager_hosted_zone_arns = ["arn:${data.aws_partition.current.partition}:route53:::hostedzone/${var.hosted_zone_id}"]

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["cert-manager:cert-manager"]
    }
  }
}

module "external_dns_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"
  tags    = var.tags

  role_name                     = "${var.environment}_${var.cluster_name}_external_dns"
  attach_external_dns_policy    = true
  external_dns_hosted_zone_arns = ["arn:${data.aws_partition.current.partition}:route53:::hostedzone/${var.hosted_zone_id}"]

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["external-dns:external-dns"]
    }
  }
}

module "cluster_autoscaler_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"
  tags    = var.tags

  count                            = var.cluster_autoscaler ? 1 : 0
  role_name                        = "${var.environment}_${var.cluster_name}_autoscaler_role"
  attach_cluster_autoscaler_policy = true
  cluster_autoscaler_cluster_names = [module.eks.cluster_name]

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:cluster-autoscaler"]
    }
  }
}


resource "local_file" "kubeconfig" {
  filename             = "${var.terragrunt_dir}/../../../kubeconfig.yaml"
  file_permission      = "0600"
  directory_permission = "0700"
  content = templatefile("${path.module}/kubeconfig.tpl", {
    endpoint                   = module.eks.cluster_endpoint
    certificate_authority_data = module.eks.cluster_certificate_authority_data
    cluster_name               = module.eks.cluster_name
    region                     = var.region
    aws_profile                = var.aws_profile
  })
}

# Upstream v3.6.2 policy, matching the umbrella chart pin. Update both together.
resource "aws_iam_policy" "load_balancer_controller" {
  name   = "${var.environment}-${var.cluster_name}-load-balancer-controller"
  policy = file("${path.module}/lb-controller-policy.json")
  tags   = var.tags
}
