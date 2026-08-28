# ---------------------------------------------------------------------------
# Default VPC (the agreed "default VPC, no NAT" model).
# ---------------------------------------------------------------------------
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ---------------------------------------------------------------------------
# Security groups
# ---------------------------------------------------------------------------

# The database. No inline ingress — access is granted only by the rules below,
# from the batch-task SG and (optionally) the bastion SG.
resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "Postgres for basketball-analytics"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-rds" }
}

# Fargate batch tasks (migrate | ingest | export | test). Egress only; they run
# in public subnets with a public IP so they can reach ECR / Secrets Manager /
# S3 without a NAT gateway.
resource "aws_security_group" "batch_tasks" {
  name        = "${local.name}-batch-tasks"
  description = "basketball-analytics batch tasks (egress only)"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-batch-tasks" }
}

resource "aws_security_group_rule" "rds_from_batch_tasks" {
  type                     = "ingress"
  security_group_id        = aws_security_group.rds.id
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.batch_tasks.id
  description              = "Postgres from Fargate batch tasks"
}

# ---------------------------------------------------------------------------
# Optional SSM jump host — for ad-hoc psql / a GUI from your laptop.
#   aws ssm start-session --target <id> \
#     --document-name AWS-StartPortForwardingSessionToRemoteHost \
#     --parameters '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5432"]}'
# ---------------------------------------------------------------------------
resource "aws_security_group" "bastion" {
  count       = var.create_bastion ? 1 : 0
  name        = "${local.name}-bastion"
  description = "SSM jump host (egress only, no inbound)"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-bastion" }
}

resource "aws_security_group_rule" "rds_from_bastion" {
  count                    = var.create_bastion ? 1 : 0
  type                     = "ingress"
  security_group_id        = aws_security_group.rds.id
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.bastion[0].id
  description              = "Postgres from the SSM bastion"
}

data "aws_ssm_parameter" "al2023_arm64" {
  count = var.create_bastion ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "bastion" {
  count                       = var.create_bastion ? 1 : 0
  ami                         = data.aws_ssm_parameter.al2023_arm64[0].value
  instance_type               = var.bastion_instance_type
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.bastion[0].id]
  iam_instance_profile        = aws_iam_instance_profile.bastion[0].name
  associate_public_ip_address = true

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  tags = { Name = "${local.name}-ssm-bastion" }
}
