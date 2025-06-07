# Multi-Cloud K8S IAC

A single repository to deploy on (different cloud providers) EKS, a Kubernetes cluster, and initial tools.

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Installation and Usage](#usage)
- [Details](#details)

---
## Requirements
 - Docker Desktop.
 - AWS Account (access key, secret access key).
---
## Installation and Usage

To install and set up the project, follow these steps:

1. Clone the repository.
2. create an `.env` file based on the [example](.env_sample) at the root of the repository.
3. Create a config.yaml file inside the `./dev` check [example](.config.yaml_example).
4. Run `docker-compose run terraform-container`.
5. Run `terragrunt run-all apply`.
---
## Details
### Why terragrunt?
The `kubernetes_manifest` does not play nice with dependencies. The stage approach using Terragrunt allows you to wait for the resources to be deployed before moving to the next stage.

### How does it work?
The installation has four stages. When the four stages are completed, the cluster will install an umbrella repository, which will install applications and tools inside the cluster.

**1. Network**
    VPC, Subenets

#### Inputs
| Name | Description | Type |
|---|---|---|
| vpc_cidr | CIDR block for the VPC. | string |
| vpc_name | Name for the VPC. | string |
| cluster_name | Name for the cluster. | string |
| domain | Name for the domain. | string |
| tags | List of tags for the module. | map(string) |
| environment | The environment where the resources will be deployed. | string |

#### Outputs
| Name | Description | Type |
|---|---|---|
| vpc_id | The ID of the created VPC. | string |
| private_subnets_ids | The IDs of the created private subnets. | list(string) |
| intra_subnets_ids | The IDs of the created internal subnets. | list(string) |  | public_subnets_ids | The IDs of the created public subnets. | list(string) |

**2. EKS**
    EKS Cluster, IAM Roles and policies, Nodes
    when this stage is ready it does provides the kubeconfig on a file in the dev folder.

#### Inputs

| Name | Description | Type |
|---|---|---|
| cluster_name | The name for your EKS cluster. | string |
| vpc_id | The ID of the created VPC. | string |
| subnet_ids | A list of subnet IDs where the EKS cluster will be deployed. | list(string) |
| control_plane_subnet_ids | (Optional) A list of subnet IDs for the EKS control plane nodes. Defaults to `subnet_ids`. | list(string) |
| tags | List of tags for the module. | map(string) |
| region | Cluster Region. | string |
| terragrunt_dir | (Optional) The directory where the Terragrunt configuration is located. | string |
| environment | The environment where the resources will be deployed. | string |

#### Outputs

| Name | Description | Type |
|---|---|---|
| eks_cluster_name | The name of the EKS cluster. | string |
| eks_cluster_endpoint | The endpoint of the EKS cluster. | string |
| eks_cluster_security_group_ids | (List) The security group IDs associated with the EKS cluster. | list(string) |  | eks_cluster_id | The EKS cluster id. | string |
| eks_cluster_certificate_authority_data | Base64 encoded certificate data required to communicate with the cluster. | string |
| eks_lb_role_arn | The lb role arn. | string |
| eks_cm_role_arn | The cm role arn. | string |
| eks_external_dns_role_arn | The external-dns role arn. | string |
| cluster_autoscaler_role_arn | The cluster auto scaler role arn. | string |


**3. Kubernetes and Helm provider**
    Install Flux

#### Inputs

| Name | Description | Type |
|---|---|---|
| region | Cluster Region. | string |
| host | The endpoint of the EKS cluster. | string |
| cluster_ca_cert | Base64 encoded certificate data required to communicate with the cluster. | string |
| cluster_name | The name of the EKS cluster. (Optional if using host and cluster_ca_cert) | string |

**4. Kubernetes resources**
    Last stage, since the resources created on this stage are flux CRDs do not wait for the flux to be ready they are created last, this stage also creates a configmap used by helm to parametrisize several installations.

#### Inputs

| Name | Description | Type |
|---|---|---|
| region | Cluster Region. | string |
| host | The endpoint of the EKS cluster. (Optional) | string |
| cluster_ca_cert | Base64 encoded certificate data required to communicate with the cluster. (Optional) | string |
| cluster_name | The name of the EKS cluster. | string |
| domain | Name for the domain. | string |
| vpc_id | The ID of the created VPC. | string |
| eks_lb_role_arn | The lb role arn. | string |
| eks_cm_role_arn | The cm role arn. | string |
| eks_external_dns_role_arn | The external-dns role arn. | string |
| cluster_autoscaler_role_arn | The cluster auto scaler role arn. | string |
| hosted_zone_id | Hosted Zone Id for the configured domain. | string |
| environment | The environment where the resources will be deployed. | string |
| repository | The repository where the resources are stored. | string |
| branch | The branch of the repository. | string |
| app_name | The name of the application. | string |
