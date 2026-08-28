variable "region" {
  description = "AWS region for all resources."
  type        = string
  default     = "eu-central-1"
}

variable "project" {
  description = "Name prefix for all resources."
  type        = string
  default     = "bball"
}

variable "tags" {
  description = "Extra tags merged into every resource's default_tags."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial gp3 storage (GB). Autoscales up to db_max_allocated_storage."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  type    = number
  default = 100
}

variable "db_engine_version" {
  description = "Postgres major version (RDS applies the latest supported minor)."
  type        = string
  default     = "16"
}

variable "db_name" {
  type    = string
  default = "analytics_db"
}

variable "db_username" {
  type    = string
  default = "bball_admin"
}

variable "db_deletion_protection" {
  description = "Blocks `terraform destroy` of the DB until set false and applied."
  type        = bool
  default     = true
}

variable "db_backup_retention_period" {
  description = "Automated backup retention (days). AWS Free Plan caps this at 1; raise to 7+ once the account is upgraded."
  type        = number
  default     = 1
}

# ---------------------------------------------------------------------------
# DB access from a laptop
# ---------------------------------------------------------------------------
# The DB is never publicly_accessible. The primary way to run DB-touching jobs
# is `aws ecs run-task` (the batch task runs inside the VPC). For ad-hoc psql /
# a GUI, set create_bastion = true to get a tiny SSM-managed jump host and use
# `aws ssm start-session ... AWS-StartPortForwardingSessionToRemoteHost`.
variable "create_bastion" {
  type    = bool
  default = false
}

variable "bastion_instance_type" {
  type    = string
  default = "t4g.nano"
}

# ---------------------------------------------------------------------------
# Batch (Fargate) task sizing
# ---------------------------------------------------------------------------
variable "batch_task_cpu" {
  type    = number
  default = 512
}

variable "batch_task_memory" {
  type    = number
  default = 1024
}

variable "batch_season" {
  description = "Default SEASON env var baked into the batch task definition."
  type        = string
  default     = "2023-2024"
}

# ---------------------------------------------------------------------------
# CI / deploy identity (optional)
# ---------------------------------------------------------------------------
variable "github_repo" {
  description = "owner/repo — when set, creates a GitHub OIDC deploy role for .github/workflows/deploy.yml."
  type        = string
  default     = ""
}

variable "create_github_oidc_provider" {
  description = "Create the account's GitHub OIDC provider. Set false if it already exists."
  type        = bool
  default     = true
}

variable "create_deploy_user" {
  description = "Also create a plain IAM user with the deployer policy (make its access key in the console)."
  type        = bool
  default     = false
}
