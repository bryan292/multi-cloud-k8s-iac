provider "aws" {
  region = var.region
}

provider "helm" {
  kubernetes {
    host                   = var.host
    cluster_ca_certificate = base64decode(var.cluster_ca_cert)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      args        = ["eks", "get-token", "--cluster-name", var.cluster_name, "--region", var.region]
      command     = "aws"
    }
  }
}

provider "kubernetes" {
  host                   = var.host
  cluster_ca_certificate = base64decode(var.cluster_ca_cert)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    args        = ["eks", "get-token", "--cluster-name", var.cluster_name, "--region", var.region]
    command     = "aws"
  }
}

resource "kubernetes_namespace" "argocd" {
  metadata {
    name = "argocd"
  }
}

resource "kubernetes_namespace" "cert-manager" {
  metadata {
    name = "cert-manager"
  }
}

resource "kubernetes_service_account" "load-balancer-service-account" {
  metadata {
    name      = "aws-load-balancer-controller"
    namespace = "kube-system"
    labels = {
      "app.kubernetes.io/name"      = "aws-load-balancer-controller"
      "app.kubernetes.io/component" = "controller"
    }
    annotations = {
      "eks.amazonaws.com/role-arn"               = var.eks_lb_role_arn
      "eks.amazonaws.com/sts-regional-endpoints" = "true"
    }
  }
}

resource "kubernetes_service_account" "cert-manager-service-account" {
  metadata {
    name      = "cert-manager"
    namespace = "cert-manager"
    labels = {
      "app.kubernetes.io/name"      = "cert-manager"
      "app.kubernetes.io/component" = "controller"
    }
    annotations = {
      "eks.amazonaws.com/role-arn"   = var.eks_cm_role_arn
      "app.kubernetes.io/managed-by" = "Helm"
    }
  }
}

resource "kubernetes_service_account" "external-dns-service-account" {
  metadata {
    name      = "external-dns"
    namespace = "external-dns"
    labels = {
      "app.kubernetes.io/name"      = "external-dns"
      "app.kubernetes.io/component" = "controller"
    }
    annotations = {
      "eks.amazonaws.com/role-arn"   = var.eks_external_dns_role_arn
      "app.kubernetes.io/managed-by" = "Helm"
    }
  }
}

resource "helm_release" "lb" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  namespace  = "kube-system"

  set {
    name  = "region"
    value = var.region
  }

  set {
    name  = "vpcId"
    value = var.vpc_id
  }

  set {
    name  = "serviceAccount.create"
    value = "false"
  }

  set {
    name  = "serviceAccount.name"
    value = "aws-load-balancer-controller"
  }

  set {
    name  = "clusterName"
    value = var.cluster_name
  }

  set {
    name  = "createIngressClassResource"
    value = false
  }
  set {
    name  = "enableCertManager"
    value = true
  }
}

resource "helm_release" "cert_manager" {
  name       = "cert-manager"
  repository = "https://charts.jetstack.io"
  chart      = "cert-manager"
  namespace  = "cert-manager"
  version    = "1.13.3"

  set {
    name  = "installCRDs"
    value = "true"
  }

  set {
    name  = "namespace"
    value = "cert-manager"
  }

  set {
    name  = "serviceAccount.create"
    value = "false"
  }

  set {
    name  = "serviceAccount.name"
    value = "cert-manager"
  }
}

resource "kubernetes_namespace" "external_dns" {
  metadata {
    name = "external-dns"
  }
}

resource "helm_release" "external_dns" {
  name       = "external-dns"
  repository = "https://kubernetes-sigs.github.io/external-dns/"
  chart      = "external-dns"
  namespace  = "external-dns"
  version    = "1.14.3" 
  set {
    name  = "provider"
    value = "aws"
  }

  set {
    name  = "domainFilters[0]"
    value = "${var.domain}"
  }

  set {
    name  = "aws.assumeRoleArn"
    value = "${var.eks_external_dns_role_arn}"
  }

  set {
    name  = "serviceAccount.create"
    value = "false"
  }

  set {
    name  = "serviceAccount.name"
    value = "external-dns"
  }

}


resource "kubernetes_manifest" "cluster_issuer" {
  depends_on = [ helm_release.cert_manager ]
  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata = {
      name = "letsencrypt-prod"
    }
    spec = {
      acme = {
        email  = "bcerdas292@outlook.com"
        server = "https://acme-v02.api.letsencrypt.org/directory"
        privateKeySecretRef = {
          name = "letsencrypt-prod"
        }
        solvers = [{
          http01 = {
            ingress = {
              class = "alb"
            }
          }
        }]
      }
    }
  }
}


resource "helm_release" "argocd" {
  name       = "argocd"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  namespace  = "argocd"
  # values = [
  #   "${file("${path.module}/chart/values.yaml")}"
  # ]
  set {
    name  = "server.ingress.hosts[0]"
    value = "argocd-${var.cluster_name}.${var.domain}"
  }

}

resource "kubernetes_manifest" "argocd_ingress" {
  manifest = {
    apiVersion = "networking.k8s.io/v1"
    kind       = "Ingress"
    metadata = {
      name      = "argocd-ingress"
      namespace = "argocd"
      annotations = {
        "kubernetes.io/ingress.class"                  = "alb"
        "alb.ingress.kubernetes.io/scheme"             = "internet-facing"
        "alb.ingress.kubernetes.io/target-type"        = "ip"
        "alb.ingress.kubernetes.io/listen-ports"       = jsonencode([{"HTTP": 80}, {"HTTPS": 443}])
        "cert-manager.io/cluster-issuer"               = "letsencrypt-prod" # For automatic SSL certificate provisioning
      }
    }
    spec = {
      rules = [
        {
          host = "argocd-${var.cluster_name}.${var.domain}"
          http = {
            paths = [
              {
                path     = "/"
                pathType = "Prefix"
                backend = {
                  service = {
                    name = "argocd-server"
                    port = {
                      number = 80
                    }
                  }
                }
              }
            ]
          }
        }
      ]
      tls = [
        {
          hosts = [
            "argocd-${var.cluster_name}.${var.domain}"
          ]
          secretName = "argocd-${var.cluster_name}-tls" # The name of the secret that cert-manager will create or use
        }
      ]
    }
  }
}


# resource "kubernetes_ingress" "argocd_ingress" {
#   metadata {
#     name      = "argocd-ingress"
#     namespace = "argocd"
#     annotations = {
#       "alb.ingress.kubernetes.io/listen-ports"       = "[{\"HTTP\": 80}, {\"HTTPS\":443}]"
#       "alb.ingress.kubernetes.io/load-balancer-name" = "argocd-ingress"
#       "alb.ingress.kubernetes.io/scheme"             = "internet-facing"
#       "alb.ingress.kubernetes.io/ssl-redirect"       = "443"
#       "alb.ingress.kubernetes.io/target-type"        = "ip"
#       "cert-manager.io/cluster-issuer"               = "letsencrypt-prod"
#       "kubernetes.io/ingress.class"                  = "alb"
#     }
#   }

#   spec {
#     rule {
#       http {
#         path {
#           path        = "/*"
#           path_type   = "ImplementationSpecific"
#           backend {
#             service {
#               name = "argocd-server"
#               port {
#                 number = 80
#               }
#             }
#           }
#         }
#       }
#     }
#   }
# }


# resource "kubernetes_manifest" "argocd_application" {
#   depends_on = [helm_release.argocd]
#   manifest = {
#     apiVersion = "argoproj.io/v1alpha1"
#     kind       = "Application"
#     metadata = {
#       name      = "helm-umbrella-charts"
#       namespace = "argocd"
#     }
#     spec = {
#       # Your application spec here
#       project = "default"
#       source = {
#         repoURL        = "https://github.com/bryan292/helm-umbrella-charts.git"
#         targetRevision = "main"
#         path           = "chart"
#       }
#       destination = {
#         server    = "https://kubernetes.default.svc"
#       }
#       syncPolicy = {
#         automated = {
#           prune    = true
#           selfHeal = true
#         }
#       }
#     }
#   }
# }
