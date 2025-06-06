provider "kubernetes" {
  host                   = var.host
  cluster_ca_certificate = base64decode(var.cluster_ca_cert)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    args        = ["eks", "get-token", "--cluster-name", var.cluster_name, "--region", var.region]
    command     = "aws"
  }
}
resource "kubernetes_manifest" "gitrepository" {
  manifest = {
    apiVersion = "source.toolkit.fluxcd.io/v1beta1"
    kind       = "GitRepository"
    metadata = {
      name      = "helm-umbrella-charts"
      namespace = "flux-system"
    }
    spec = {
      interval = "1m"
      url      = "https://github.com/bryan292/helm-umbrella-charts"
      ref = {
        branch = "main"
      }
    }
  }
}

resource "kubernetes_manifest" "helmrelease" {
  manifest = {
    apiVersion = "helm.toolkit.fluxcd.io/v2beta1"
    kind       = "HelmRelease"
    metadata = {
      name      = "umbrella-chart-release"
      namespace = "default"
    }
    spec = {
      interval = "1m"
      chart = {
        spec = {
          chart = "./chart" # Adjust the path to where your umbrella chart is located within the repository
          sourceRef = {
            kind      = "GitRepository"
            name      = "helm-umbrella-charts"
            namespace = "flux-system"
          }

        }
      }
    }
  }
}

resource "kubernetes_config_map" "cert_manager_config" {
  metadata {
    name      = "remote-config"
    namespace = "flux-system"
  }

  data = {
    "eks_cm_role_arn"              = var.eks_cm_role_arn
    "eks_lb_role_arn"              = var.eks_lb_role_arn
    "eks_external_dns_role_arn"    = var.eks_external_dns_role_arn
    "cluster_autoscaler_role_arn"  = var.cluster_autoscaler_role_arn
    "cluster_name"                 = var.cluster_name
    "domain"                       = var.domain
    "hosted_zone_id"               = var.hosted_zone_id
    "region"                       = var.region
    "vpc_id"                       = var.vpc_id
    "environment"                  = var.environment
    "repository"                   = var.repository
    "branch"                       = var.branch
    "app_name"                     = var.app_name
    "cluster_autoscaler"           = var.cluster_autoscaler
    "email"                        = var.email
    "external_dns"                 = var.external_dns
    "metrics_server"               = var.metrics_server
    "cert_manager"                 = var.cert_manager
    "prometheus"                   = var.prometheus
    "grafana"                      = var.grafana
    "loki"                         = var.loki
    "aws_load_balancer_controller" = var.aws_load_balancer_controller
    "weave_gitops"                 = var.weave_gitops
    "custom_app"                   = var.custom_app
  }
}
