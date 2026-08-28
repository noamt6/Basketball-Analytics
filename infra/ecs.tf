# Fargate batch runner — no service, just a task definition invoked on demand:
#   aws ecs run-task ... --overrides '{"containerOverrides":[{"name":"app","command":["migrate"]}]}'
# Commands: migrate | ingest | export | test  (see docker-entrypoint.sh).
resource "aws_cloudwatch_log_group" "batch" {
  name              = "/ecs/${local.name}-batch"
  retention_in_days = 14
}

resource "aws_ecs_cluster" "batch" {
  name = "${local.name}-batch"
}

resource "aws_ecs_task_definition" "batch" {
  family                   = "${local.name}-batch"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.batch_task_cpu
  memory                   = var.batch_task_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "app"
    image     = "${aws_ecr_repository.batch.repository_url}:latest"
    essential = true
    # `command` is supplied per `aws ecs run-task`.
    environment = [
      { name = "DB_SECRET_ARN", value = aws_secretsmanager_secret.db.arn },
      { name = "AWS_REGION", value = var.region },
      { name = "DB_SSLMODE", value = "require" },
      { name = "SEASON", value = var.batch_season },
      { name = "SITE_BUCKET", value = aws_s3_bucket.site.bucket },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.batch.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "app"
      }
    }
  }])
}
