locals {
  config = yamldecode(file("${get_repo_root()}/config.yaml"))
  aws_config = try(local.config.aws, {})
  kubernetes_version = try(local.aws_config.kubernetes_version, local.aws_config.global.kubernetes_version)
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
    key            = "~${local.aws_config.global.cluster_name}/${local.aws_config.global.environment}/${path_relative_to_include()}/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "${local.aws_config.global.environment}-${local.aws_config.global.cluster_name}"
  }
}
