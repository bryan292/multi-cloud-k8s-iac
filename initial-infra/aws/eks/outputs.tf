output "eks_cluster_name" {
  description = "The name of the EKS cluster."
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "The endpoint of the EKS cluster."
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_security_group_ids" {
  description = "The security group IDs associated with the EKS cluster."
  value       = module.eks.cluster_security_group_id
}

output "eks_cluster_id" {
  description = "The EKS cluster id."
  value       = module.eks.cluster_id
}

output "eks_cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster."
  value       = module.eks.cluster_certificate_authority_data
}

output "eks_lb_role_arn" {
  description = "The lb role arn."
  value       = module.lb_role.iam_role_arn
}

output "eks_cm_role_arn" {
  description = "The cm role arn."
  value       = module.cm_role.iam_role_arn
}

output "eks_external_dns_role_arn" {
  description = "The external-dns role arn."
  value       = module.external_dns_role.iam_role_arn
}

output "cluster_autoscaler_role_arn" {
  description = "The cluster auto scaler role arn."
  value       = module.cluster_autoscaler_role.iam_role_arn
}


# output "eks_node_group_name" {
#   description = "The name of the EKS node group."
#   value       = aws_eks_node_group.eks_node_group.node_group_name
# }
