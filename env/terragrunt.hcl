locals {
  config = yamldecode(file("${get_repo_root()}/config.yaml"))
  kubernetes_version = try(local.config.kubernetes_version, local.config.global.kubernetes_version)
}

inputs = {
  kubernetes_version = local.kubernetes_version
}


remote_state {
  backend = "s3"
  generate = {
    path      = "state.tf"
    if_exists = "overwrite"
  }
  config = {
    bucket         = "multi-cloud-k8s-iac"
    key            = "~${local.config.global.cluster_name}/${local.config.global.environment}/${path_relative_to_include()}/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "${local.config.global.environment}-${local.config.global.cluster_name}"
  }
}
