resource "aws_security_group" "eks" {
  name        = "${var.environment}_${var.cluster_name}_eks_cluster"
  description = "Allow traffic"
  vpc_id      = var.vpc_id

  ingress {
    description      = "World"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = var.tags
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.27.0"

  cluster_name                             = "${var.environment}-${var.cluster_name}" # EKS cluster name creted based on the environment and cluster name
  cluster_version                          = var.kubernetes_version
  enable_cluster_creator_admin_permissions = true
  iam_role_additional_policies = {
    additional = aws_iam_policy.additional.arn
  }

  vpc_id                   = var.vpc_id # VPC ID where the cluster and workers will be deployed, received from the netwrork module
  subnet_ids               = var.subnet_ids
  control_plane_subnet_ids = var.control_plane_subnet_ids

  cluster_endpoint_public_access        = true
  cluster_additional_security_group_ids = [aws_security_group.eks.id]
  # Extend cluster security group rules
  cluster_security_group_additional_rules = {
    ingress_nodes_ephemeral_ports_tcp = {
      description                = "Nodes on ephemeral ports"
      protocol                   = "tcp"
      from_port                  = 1025
      to_port                    = 65535
      type                       = "ingress"
      source_node_security_group = true
    }

    ingress_source_security_group_id = {
      description              = "Ingress from another computed security group"
      protocol                 = "tcp"
      from_port                = 22
      to_port                  = 22
      type                     = "ingress"
      source_security_group_id = aws_security_group.additional.id
    }
    ingress_alow_remote_access = {
      description              = "Ingress to allow remote access to the cluster"
      protocol                 = "tcp"
      from_port                = 6443
      to_port                  = 6443
      type                     = "ingress"
      source_security_group_id = aws_security_group.additional.id
    }

  }

  # Extend node-to-node security group rules
  node_security_group_additional_rules = {
    ingress_self_all = {
      description = "Node to node all ports/protocols"
      protocol    = "-1"
      from_port   = 0
      to_port     = 0
      type        = "ingress"
      self        = true
    }

    ingress_source_security_group_id = {
      description              = "Ingress from another computed security group"
      protocol                 = "tcp"
      from_port                = 22
      to_port                  = 22
      type                     = "ingress"
      source_security_group_id = aws_security_group.additional.id
    }
  }

  node_security_group_tags = { # Tags for the node security group, used by the aws load balancer controller
    "kubernetes.io/cluster/${var.environment}-${var.cluster_name}" = null
  }

  eks_managed_node_group_defaults = { # Default values for the managed node group
    ami_type                              = "AL2_x86_64"
    instance_types                        = ["t3.small", "t3.medium", "m5.large", "m5n.large", "m5zn.large"]
    attach_cluster_primary_security_group = true
    vpc_security_group_ids                = [aws_security_group.additional.id]
    iam_role_additional_policies = {
      additional = aws_iam_policy.additional.arn
    }
  }

  eks_managed_node_groups = {
    worker_nodes = { # Managed node group configuration, using spot instances for cost savings
      name = "${var.environment}-${var.cluster_name}-w"

      instance_types = ["t3.medium"]
      capacity_type  = "SPOT"
      min_size       = 1
      max_size       = 3
      desired_size   = 2
    }

    # two = {
    #   name = "${var.environment}-${var.cluster_name}-2"

    #   instance_types = ["t3.medium"]
    #   capacity_type  = "SPOT"
    #   min_size       = 1
    #   max_size       = 5
    #   desired_size   = 3
    # }
  }

  tags = var.tags

}

data "aws_iam_policy" "ebs_csi_policy" {
  arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

module "irsa-ebs-csi" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-assumable-role-with-oidc"
  version = "4.7.0"

  create_role                   = true
  role_name                     = "AmazonEKSTFEBSCSIRole-${module.eks.cluster_name}"
  provider_url                  = module.eks.oidc_provider
  role_policy_arns              = [data.aws_iam_policy.ebs_csi_policy.arn]
  oidc_fully_qualified_subjects = ["system:serviceaccount:kube-system:ebs-csi-controller-sa"]
}

resource "aws_eks_addon" "ebs-csi" {
  cluster_name             = module.eks.cluster_name
  addon_name               = "aws-ebs-csi-driver"
  addon_version            = "v1.20.0-eksbuild.1"
  service_account_role_arn = module.irsa-ebs-csi.iam_role_arn
  tags = {
    "eks_addon" = "ebs-csi"
    "terraform" = "true"
  }
}

resource "aws_security_group" "additional" {
  name_prefix = "${var.environment}-${var.cluster_name}-additional"
  vpc_id      = var.vpc_id

  ingress {
    from_port = 22
    to_port   = 22
    protocol  = "tcp"
    cidr_blocks = [
      "10.0.0.0/8",
      "172.16.0.0/12",
      "192.168.0.0/16",
    ]
  }

  tags = merge(var.tags, { Name = "${var.cluster_name}-additional" })
}

resource "aws_iam_policy" "additional" {
  name = "${var.environment}-${var.cluster_name}-additional"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "ec2:Describe*",
        ]
        Effect   = "Allow"
        Resource = "*"
      },
    ]
  })
}

# Create the IAM roles for the service accounts
module "lb_role" {
  source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"

  role_name                              = "${var.environment}_${var.cluster_name}_lb"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }
}

module "cm_role" {
  source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"

  role_name                  = "${var.environment}_${var.cluster_name}_cm"
  attach_cert_manager_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["cert-manager:cert-manager"]
    }
  }
}

module "external_dns_role" {
  source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"

  role_name                  = "${var.environment}_${var.cluster_name}_external_dns"
  attach_external_dns_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["external-dns:external-dns"]
    }
  }
}

module "cluster_autoscaler_role" {
  source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"

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

# Createa a kubeconfig file that can  be used by kubectl
resource "local_file" "kubeconfig" {
  filename = "${var.terragrunt_dir}/../../kubeconfig.yaml"
  content = templatefile("${var.terragrunt_dir}/../../../initial-infra/aws/kubeconfig/kubeconfig.tpl", {
    endpoint                   = module.eks.cluster_endpoint
    certificate_authority_data = module.eks.cluster_certificate_authority_data
    cluster_name               = "${var.environment}-${var.cluster_name}"
    region                     = var.region
  })
}
