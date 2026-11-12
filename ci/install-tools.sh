#!/usr/bin/env bash
# GitHub ubuntu-24.04 x64 only; tools match the validated container versions.
set -euo pipefail
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]]
task_tools_dir="${RUNNER_TEMP:?}/iac-tools-${GITHUB_RUN_ID:?}"
mkdir -p "$task_tools_dir/bin"
# Reuse the checksum-verified build rather than maintaining a second installer.
docker build -t iac-hosted-tools .
task_tools_container="$(docker create iac-hosted-tools)"
trap 'docker rm -f "$task_tools_container" >/dev/null 2>&1 || true' EXIT
for tool in terraform terragrunt helm kubectl; do
  docker cp "$task_tools_container:/usr/local/bin/$tool" "$task_tools_dir/bin/$tool"
done
curl -fsSL https://s3.amazonaws.com/session-manager-downloads/plugin/1.2.896.0/ubuntu_64bit/session-manager-plugin.deb -o "$task_tools_dir/ssm.deb"
printf '%s  %s\n' 53f51fcc67314a4bf85888a38a3967cd41f8d0f28a60a9469a63acf935ba713e "$task_tools_dir/ssm.deb" | sha256sum -c -
dpkg-deb -x "$task_tools_dir/ssm.deb" "$task_tools_dir/ssm"
ln -sf "$task_tools_dir/ssm/usr/local/sessionmanagerplugin/bin/session-manager-plugin" "$task_tools_dir/bin/session-manager-plugin"
curl -fsSL https://github.com/Azure/kubelogin/releases/download/v0.2.22/kubelogin-linux-amd64.zip -o "$task_tools_dir/kubelogin.zip"
printf '%s  %s\n' 716cbcb1880bca8f0e976b8917d06fcfe04de2c1e737eaaabbb26e2782330119 "$task_tools_dir/kubelogin.zip" | sha256sum -c -
unzip -oq "$task_tools_dir/kubelogin.zip" -d "$task_tools_dir/kubelogin"
cp "$task_tools_dir/kubelogin/bin/linux_amd64/kubelogin" "$task_tools_dir/bin/"
chmod +x "$task_tools_dir/bin/"*
python3 -m venv "$task_tools_dir/venv"
"$task_tools_dir/venv/bin/pip" install -r requirements.txt
printf '%s\n%s\n' "$task_tools_dir/bin" "$task_tools_dir/venv/bin" >> "$GITHUB_PATH"
for tool in az aws gh gpg; do command -v "$tool" >/dev/null; done
