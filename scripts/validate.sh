#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
terraform fmt -check -recursive infrastructure-modules
terraform fmt -check bootstrap
terraform -chdir=bootstrap init -backend=false -input=false -lockfile=readonly
terraform -chdir=bootstrap validate
terragrunt hcl fmt --check --working-dir deployment-config
for module in aws/network aws/eks kubernetes kube_resources; do
  terraform -chdir="infrastructure-modules/$module" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="infrastructure-modules/$module" validate
  terraform -chdir="infrastructure-modules/$module" test
 done
python3 -m unittest discover -s tests -p 'test_*.py'

bash -n scripts/*.sh
python3 -m py_compile scripts/*.py
