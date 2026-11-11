#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
terraform fmt -check -recursive infrastructure-modules
terraform fmt -check bootstrap
terraform -chdir=bootstrap init -backend=false -input=false -lockfile=readonly
terraform -chdir=bootstrap validate
terraform -chdir=bootstrap/azure init -backend=false -input=false -lockfile=readonly
terraform -chdir=bootstrap/azure validate
terragrunt hcl fmt --check --working-dir deployment-config
for module in aws/network aws/eks azure/aks kubernetes kube_resources; do
  terraform -chdir="infrastructure-modules/$module" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="infrastructure-modules/$module" validate
  terraform -chdir="infrastructure-modules/$module" test
 done
if python3 -c 'import yaml' 2>/dev/null; then
  python3 -m unittest discover -s tests -p 'test_*.py'
elif command -v uv >/dev/null 2>&1; then
  uv run --with pyyaml python -m unittest discover -s tests -p 'test_*.py'
else
  echo "PyYAML is required for Python validation tests" >&2
  exit 1
fi

bash -n scripts/*.sh
python3 -m py_compile scripts/*.py
