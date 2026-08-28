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
    apply_method = "immediate" # rds.force_ssl is dynamic on Postgres — no reboot needed
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name}-pg"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  parameter_group_name    = aws_db_parameter_group.main.name
  publicly_accessible     = false
  multi_az                = false

  backup_retention_period    = var.db_backup_retention_period
  auto_minor_version_upgrade = true
  apply_immediately          = true
  deletion_protection        = var.db_deletion_protection

  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-pg-final"
}
