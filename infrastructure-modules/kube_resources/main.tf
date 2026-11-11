provider "kubernetes" {
  host                   = var.kubeconfig_path == null ? var.host : null
  cluster_ca_certificate = var.kubeconfig_path == null ? base64decode(var.cluster_ca_cert) : null
  config_path            = var.kubeconfig_path

  dynamic "exec" {
    for_each = var.kubeconfig_path == null ? [1] : []
    content {
      api_version = "client.authentication.k8s.io/v1beta1"
      args        = ["eks", "get-token", "--cluster-name", var.cluster_name, "--region", var.region]
      command     = "aws"
      env         = { AWS_PROFILE = var.aws_profile }
    }
  }
}

resource "kubernetes_storage_class_v1" "gp3" {
  count = var.create_storage_class ? 1 : 0
  metadata {
    name = "gp3"
  }
  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Retain"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true
  parameters = {
    type               = "gp3"
    encrypted          = "true"
    tagSpecification_1 = "BackupCluster=${var.cluster_name}"
  }
}

# Transfer existing platform objects out of Terraform state without deleting
# their live resources. Flux assumes ownership from the immutable Git source.
removed {
  from = kubernetes_manifest.helm_repository
  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_manifest.helm_release
  lifecycle {
    destroy = false
  }
}

resource "kubernetes_manifest" "platform_source" {
  manifest = {
    apiVersion = "source.toolkit.fluxcd.io/v1"
    kind       = "GitRepository"
    metadata   = { name = "helm-umbrella-charts", namespace = "flux-system" }
    spec = merge(
      {
        interval = "5m"
        url      = var.platform.repository
        ref      = { commit = var.platform.commit }
      },
      var.platform.secret_name == "" ? {} : { secretRef = { name = var.platform.secret_name } }
    )
  }

  lifecycle {
    precondition {
      condition     = can(regex("^[0-9a-f]{40}$", var.platform.commit)) && startswith(var.platform.repository, "https://")
      error_message = "Platform source requires an HTTPS repository and immutable 40-character commit."
    }
  }
}

resource "kubernetes_manifest" "platform" {
  manifest = {
    apiVersion = "kustomize.toolkit.fluxcd.io/v1"
    kind       = "Kustomization"
    metadata   = { name = "helm-umbrella-charts", namespace = "flux-system" }
    spec = {
      interval      = "5m"
      retryInterval = "1m"
      path          = "./clusters/${var.environment}"
      prune         = true
      wait          = true
      timeout       = "20m"
      sourceRef     = { kind = "GitRepository", name = "helm-umbrella-charts" }
    }
  }
  depends_on = [kubernetes_manifest.platform_source, kubernetes_storage_class_v1.gp3]
}

resource "kubernetes_manifest" "application_source" {
  count = var.application.enabled ? 1 : 0
  manifest = {
    apiVersion = "source.toolkit.fluxcd.io/v1"
    kind       = "GitRepository"
    metadata   = { name = "application", namespace = "flux-system" }
    spec       = merge({ interval = "1m", url = var.application.repository, ref = { commit = var.application.commit } }, var.application.secret_name == "" ? {} : { secretRef = { name = var.application.secret_name } })
  }
  lifecycle {
    precondition {
      condition     = can(regex("^[0-9a-f]{40}$", var.application.commit)) && startswith(var.application.repository, "https://")
      error_message = "Application source requires an HTTPS repository and immutable 40-character commit."
    }
  }
}

resource "kubernetes_manifest" "application" {
  count = var.application.enabled ? 1 : 0
  manifest = {
    apiVersion = "kustomize.toolkit.fluxcd.io/v1"
    kind       = "Kustomization"
    metadata   = { name = "application", namespace = "flux-system" }
    spec = {
      interval  = "5m"
      path      = var.application.path
      prune     = true
      wait      = true
      timeout   = "10m"
      sourceRef = { kind = "GitRepository", name = "application" }
    }
  }
  depends_on = [kubernetes_manifest.application_source, kubernetes_manifest.platform]
}
