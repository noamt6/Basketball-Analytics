# ---------------------------------------------------------------------------
# Database — DECOMMISSIONED (FinOps).
#
# The RDS instance (bball-pg) and its Secrets Manager secret (bball/db) were
# deleted on purpose to cut cost; the dashboard is static (S3 + CloudFront)
# and does not need a live DB. A final snapshot was kept:
#   bball-pg-final-20260902
#
# The subnet group, parameter group and the RDS security group (network.tf)
# still exist in AWS and cost nothing, so they stay here — that keeps the
# code matching the account and makes restoring the DB a small change:
# re-add an aws_db_instance (snapshot_identifier = the snapshot above) plus a
# secret, and point DB_SECRET_ARN in ecs.tf / ReadDbSecret in iam.tf at it.
# Until then the Fargate batch task (ingest | export | migrate) has no DB.
# ---------------------------------------------------------------------------
resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db"
  subnet_ids = data.aws_subnets.default.ids
}

# Force TLS on every connection (db_client.py sends DB_SSLMODE=require).
resource "aws_db_parameter_group" "main" {
  name        = "${local.name}-pg16"
  family      = "postgres16"
  description = "basketball-analytics postgres 16"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot" # what RDS reports back for this param; matches live
  }
}
