# Use a lightweight Linux distribution as the base image
FROM alpine:3.14

USER root

# Set the Terragrunt version
ARG TERRAGRUNT_VERSION="0.54.16"

# Install necessary packages: Terraform, Helm, AWS CLI, and kubectl dependencies
RUN apk add --update --no-cache curl unzip python3 py3-pip bash git && \
    pip3 install --upgrade pip && \
    pip3 install awscli

# Install Terraform
RUN curl -LO "https://releases.hashicorp.com/terraform/1.1.5/terraform_1.1.5_linux_amd64.zip" && \
    unzip terraform_1.1.5_linux_amd64.zip -d /usr/local/bin

# Install Terragrunt
RUN wget https://github.com/gruntwork-io/terragrunt/releases/download/v${TERRAGRUNT_VERSION}/terragrunt_linux_amd64 -O /bin/terragrunt && \
    chmod +x /bin/terragrunt

# Install Helm
RUN curl -LO "https://get.helm.sh/helm-v3.14.0-linux-amd64.tar.gz" && \
    tar -zxvf helm-v3.14.0-linux-amd64.tar.gz && \
    mv linux-amd64/helm /usr/local/bin/helm

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Clean up
RUN rm -rf terraform_1.1.5_linux_amd64.zip linux-amd64 helm-v3.8.0-linux-amd64.tar.gz

# Set the working directory within the container
WORKDIR /app

# Copy your Terraform code and other necessary files into the container
COPY . /app

# Set KUBECONFIG environment variable to point to the kubeconfig file
ENV KUBECONFIG /app/env/kubeconfig.yaml

