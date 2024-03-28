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

resource "helm_release" "flux2" {
  name             = "flux2"
  repository       = "https://fluxcd-community.github.io/helm-charts"
  chart            = "flux2"
  namespace        = "flux-system"
  create_namespace = true
  version          = "2.12.2"
}
