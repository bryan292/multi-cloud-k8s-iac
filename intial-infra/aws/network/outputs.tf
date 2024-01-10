output "vpc_id" {
  description = "The ID of the created VPC."
  value       = module.network.vpc_id
}

output "private_subnets_ids" {
  description = "The IDs of the created subnets."
  value       = module.network.private_subnets
}

output "intra_subnets_ids" {
  description = "The IDs of the created subnets."
  value       = module.network.intra_subnets
}

output "public_subnets_ids" {
  description = "The IDs of the created subnets."
  value       = module.network.public_subnets
}

output "lb_dns_name" {
    value = aws_lb.lb.dns_name
}

output "lb_zone_id" {
    value = aws_lb.lb.zone_id
}
