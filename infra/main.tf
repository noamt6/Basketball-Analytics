# Account context + shared locals. Networking is in network.tf.
data "aws_caller_identity" "current" {}

locals {
  name       = var.project
  account_id = data.aws_caller_identity.current.account_id

  tags = merge({
    Project   = var.project
    ManagedBy = "terraform"
  }, var.tags)
}
