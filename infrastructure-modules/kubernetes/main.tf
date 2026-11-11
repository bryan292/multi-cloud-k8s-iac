provider "helm" {
  kubernetes = {
    host                   = var.kubeconfig_path == null ? var.host : null
    cluster_ca_certificate = var.kubeconfig_path == null ? base64decode(var.cluster_ca_cert) : null
    config_path            = var.kubeconfig_path
    exec = var.kubeconfig_path == null ? {
      api_version = "client.authentication.k8s.io/v1beta1"
      args        = ["eks", "get-token", "--cluster-name", var.cluster_name, "--region", var.region]
      command     = "aws"
    } : null
  }
}
resource "helm_release" "flux2" {
  name             = "flux2"
  repository       = "https://fluxcd-community.github.io/helm-charts"
  chart            = "flux2"
  namespace        = "flux-system"
  create_namespace = true
  version          = "2.20.0"
  atomic           = true
  cleanup_on_fail  = true
  wait             = true
  timeout          = 600
}
