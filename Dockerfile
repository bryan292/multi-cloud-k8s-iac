FROM alpine:3.22
ARG TARGETARCH
ARG TERRAFORM_VERSION=1.15.1
ARG TERRAGRUNT_VERSION=1.1.1
ARG HELM_VERSION=3.19.0
ARG KUBECTL_VERSION=1.35.0
RUN apk add --no-cache bash curl unzip git aws-cli python3 py3-pip gnupg ca-certificates
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
ENV PATH="/opt/venv/bin:$PATH"
RUN set -eu; arch="${TARGETARCH:-$(apk --print-arch)}"; \
    case "$arch" in x86_64) arch=amd64;; aarch64) arch=arm64;; esac; \
    mkdir /tmp/tools; cd /tmp/tools; \
    curl -fsSLO "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${arch}.zip"; \
    curl -fsSLO "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_SHA256SUMS"; \
    grep "terraform_${TERRAFORM_VERSION}_linux_${arch}.zip$" "terraform_${TERRAFORM_VERSION}_SHA256SUMS" | sha256sum -c -; \
    unzip "terraform_${TERRAFORM_VERSION}_linux_${arch}.zip" terraform -d /usr/local/bin; \
    curl -fsSLO "https://github.com/gruntwork-io/terragrunt/releases/download/v${TERRAGRUNT_VERSION}/terragrunt_linux_${arch}"; \
    curl -fsSLO "https://github.com/gruntwork-io/terragrunt/releases/download/v${TERRAGRUNT_VERSION}/SHA256SUMS"; \
    grep "terragrunt_linux_${arch}$" SHA256SUMS | sha256sum -c -; \
    mv "terragrunt_linux_${arch}" /usr/local/bin/terragrunt; \
    curl -fsSLO "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${arch}.tar.gz"; \
    curl -fsSLO "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${arch}.tar.gz.sha256sum"; \
    sha256sum -c "helm-v${HELM_VERSION}-linux-${arch}.tar.gz.sha256sum"; \
    tar -xzf "helm-v${HELM_VERSION}-linux-${arch}.tar.gz"; mv "linux-${arch}/helm" /usr/local/bin/helm; \
    curl -fsSL "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${arch}/kubectl" -o kubectl; \
    curl -fsSL "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${arch}/kubectl.sha256" -o kubectl.sha256; \
    printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum -c -; \
    mv kubectl /usr/local/bin/kubectl; chmod +x /usr/local/bin/terragrunt /usr/local/bin/kubectl; \
    rm -rf /tmp/tools
RUN addgroup -g 1000 tools && adduser -D -u 1000 -G tools tools
USER tools
WORKDIR /app
ENV KUBECONFIG=/app/kubeconfig.yaml
CMD ["bash"]
