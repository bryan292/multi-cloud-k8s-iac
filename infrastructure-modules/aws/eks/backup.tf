variable "enable_volume_backups" {
  description = "Daily EBS snapshots for volumes tagged with this cluster; not an application-consistent database backup."
  type        = bool
  default     = true
}
resource "aws_backup_vault" "volumes" {
  count = var.enable_volume_backups ? 1 : 0
  name  = "${var.environment}-${var.cluster_name}-volumes"
  tags  = var.tags
}
resource "aws_backup_plan" "volumes" {
  count = var.enable_volume_backups ? 1 : 0
  name  = "${var.environment}-${var.cluster_name}-daily"
  rule {
    rule_name         = "daily-ebs"
    target_vault_name = aws_backup_vault.volumes[0].name
    schedule          = "cron(0 6 * * ? *)"
    lifecycle { delete_after = 30 }
  }
  tags = var.tags
}
resource "aws_iam_role" "backup" {
  count = var.enable_volume_backups ? 1 : 0
  name  = "${var.environment}-${var.cluster_name}-backup"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "backup.amazonaws.com" } }]
  })
  tags = var.tags
}
resource "aws_iam_role_policy_attachment" "backup" {
  count      = var.enable_volume_backups ? 1 : 0
  role       = aws_iam_role.backup[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}
resource "aws_backup_selection" "volumes" {
  count        = var.enable_volume_backups ? 1 : 0
  name         = "cluster-ebs"
  plan_id      = aws_backup_plan.volumes[0].id
  iam_role_arn = aws_iam_role.backup[0].arn
  resources    = ["arn:${data.aws_partition.current.partition}:ec2:${var.region}:${var.account_id}:volume/*"]
  condition {
    string_equals {
      key   = "aws:ResourceTag/BackupCluster"
      value = "${var.environment}-${var.cluster_name}"
    }
  }
  depends_on = [aws_iam_role_policy_attachment.backup]
}
