# Use a lightweight Linux distribution as the base image
FROM alpine:3.14

USER root

# Install necessary packages: Terraform, Helm, and AWS CLI
RUN apk add --update --no-cache curl unzip python3 py3-pip bash git && \
    pip3 install --upgrade pip && \
    pip3 install awscli


RUN curl -LO "https://releases.hashicorp.com/terraform/1.1.5/terraform_1.1.5_linux_amd64.zip" && \
    unzip terraform_1.1.5_linux_amd64.zip -d /usr/local/bin

RUN curl -LO "https://get.helm.sh/helm-v3.8.0-linux-amd64.tar.gz" && \
    tar -zxvf helm-v3.8.0-linux-amd64.tar.gz && \
    mv linux-amd64/helm /usr/local/bin/helm

# Install AWS CLI
# RUN curl -LO "https://s3.amazonaws.com/aws-cli/awscli-bundle.zip" && \
#     unzip awscli-bundle.zip && \
#     ./awscli-bundle/install -i /usr/local/aws -b /usr/local/bin/aws

RUN rm -rf awscliv2.zip && \
    rm -rf terraform_1.1.5_linux_amd64.zip linux-amd64 helm-v3.7.0-linux-amd64.tar.gz

# Set the working directory within the container
WORKDIR /app

# Copy your Terraform code into the container
COPY . /app
