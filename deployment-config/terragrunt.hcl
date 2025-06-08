locals {
  config = yamldecode(file("${get_repo_root()}/config.yaml"))
  global = try(local.config.global, {})
  aws    = try(local.config.aws, {})
  kubernetes_version = try(local.global.kubernetes_version, null)
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
    bucket         = local.aws.bucket_name
    key            = "~${local.global.cluster_name}/${local.global.environment}/${path_relative_to_include()}/terraform.tfstate"
    region         = local.aws.region
    dynamodb_table = "${local.global.environment}-${local.global.cluster_name}"
  }
}
