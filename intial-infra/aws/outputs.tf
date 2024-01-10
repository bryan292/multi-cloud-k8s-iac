# Output the EKS cluster kubeconfig
# output "eks_kubeconfig" {
#   description = "The kubeconfig for connecting to the EKS cluster."
#   value       = module.eks_cluster.kubeconfig
# }

# Output other relevant information as needed
output "vpc_id" {
  description = "The ID of the created VPC."
  value       = module.network.vpc_id
}
