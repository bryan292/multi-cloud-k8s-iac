resource "aws_route53_record" "argocd_dns" {
  name    = "example.com"
  type    = "A" # Change to "CNAME" if using CNAME
  zone_id = var.route53_zone_id

  alias {
    name                   = var.dns_name
    zone_id                = var.zone_id
    evaluate_target_health = true
  }
}
