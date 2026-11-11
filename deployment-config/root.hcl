locals {
  config = yamldecode(file("${get_repo_root()}/config.yaml"))
}
remote_state {
  backend  = "s3"
  generate = { path = "state.tf", if_exists = "overwrite_terragrunt" }
  config = {
    bucket              = local.config.global.bucket_name
    key                 = "~${local.config.global.cluster_name}/${local.config.global.environment}/${path_relative_to_include()}/terraform.tfstate"
    region              = local.config.global.state_region
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = [local.config.global.account_id]
  }
}
