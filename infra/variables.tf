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

# ---------------------------------------------------------------------------
# Site / CDN (CloudFront). Defaults mirror the live distribution.
# ---------------------------------------------------------------------------
variable "site_aliases" {
  description = "Custom domain names on the distribution (empty = *.cloudfront.net only)."
  type        = list(string)
  default     = ["plusminus.cloud", "www.plusminus.cloud"]
}

variable "acm_certificate_arn" {
  description = "ACM certificate (must be in us-east-1) covering site_aliases. Required when site_aliases is set."
  type        = string
  default     = "arn:aws:acm:us-east-1:402631154156:certificate/f1362ce6-9c79-41be-900d-a50e23136695"
}

variable "geo_allow_countries" {
  description = "ISO country codes allowed to reach the site (whitelist). Empty = no geo restriction."
  type        = list(string)
  default     = ["IL"]
}

variable "cdn_log_bucket" {
  description = "Bucket name for CloudFront standard access logs. Empty = logging off."
  type        = string
  default     = "plusminus-cloudfront-logs-402631154156"
}

variable "edge_logger_function" {
  description = "Name of a CloudFront Function attached on viewer-request. Empty = none."
  type        = string
  default     = "bball-edge-logger"
}
