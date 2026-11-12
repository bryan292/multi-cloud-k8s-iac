terraform {
  source = "../../infrastructure-modules/kubernetes"
}

include "global" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

dependency "cluster" {
  config_path = include.global.locals.provider == "aws" ? "../aws/eks" : "../azure/aks"
}

inputs = {
  kubeconfig_path = get_env("IAC_KUBECONFIG", "${get_repo_root()}/kubeconfig.yaml")
}
