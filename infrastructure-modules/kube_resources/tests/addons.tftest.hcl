mock_provider "kubernetes" {}

variables {
  kubeconfig_path = "/tmp/kubeconfig"
  provider_name   = "aws"
  environment     = "dev"
  cluster_settings = {
    provider           = "aws"
    cluster_name       = "test-cluster"
    kubernetes_version = "1.35"
    storage_class      = "gp3"
  }
  platform = {
    repository = "https://github.com/example/helm-umbrella-charts.git"
    commit     = "0123456789abcdef0123456789abcdef01234567"
    path       = "./clusters/dev/aws"
  }
}

run "immutable_platform_source" {
  command = plan

  assert {
    condition     = kubernetes_manifest.platform_source.manifest.spec.ref.commit == var.platform.commit
    error_message = "The platform GitRepository must use the configured immutable commit."
  }

  assert {
    condition     = kubernetes_manifest.platform.manifest.spec.path == "./clusters/dev/aws"
    error_message = "The platform Kustomization must select the configured environment."
  }

  assert {
    condition     = kubernetes_manifest.platform.manifest.spec.sourceRef.name == "helm-umbrella-charts"
    error_message = "The platform Kustomization must consume the umbrella GitRepository."
  }
}

run "reject_mutable_platform_ref" {
  command = plan

  variables {
    platform = {
      repository = "https://github.com/example/helm-umbrella-charts.git"
      commit     = "main"
      path       = "./clusters/dev/aws"
    }
  }

  expect_failures = [kubernetes_manifest.platform_source]
}
