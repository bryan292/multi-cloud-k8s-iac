locals {
  config = yamldecode(file("config.yaml"))
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
