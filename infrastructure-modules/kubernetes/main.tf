provider "helm" {
  kubernetes = {
    config_path = var.kubeconfig_path
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
  # AKS can expose aggregated APIs whose OpenAPI discovery blocks Helm's
  # client-side validation. Kubernetes still validates every submitted object.
  disable_openapi_validation = true
  wait                       = true
  timeout                    = 600
}
