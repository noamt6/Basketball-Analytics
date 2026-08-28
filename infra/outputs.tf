output "rds_endpoint" {
  description = "host:port for the DB"
  value       = "${aws_db_instance.main.address}:${aws_db_instance.main.port}"
}

output "rds_address" {
  description = "DB hostname (use as the 'host' in an SSM port-forward)"
  value       = aws_db_instance.main.address
}

output "db_secret_arn" {
  description = "Set as DB_SECRET_ARN for db_client.py / the batch task"
  value       = aws_secretsmanager_secret.db.arn
}

output "ecr_repository_url" {
  value = aws_ecr_repository.batch.repository_url
}

output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.site.id
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.site.domain_name
}

output "cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "ecs_cluster" {
  value = aws_ecs_cluster.batch.name
}

output "ecs_task_definition" {
  value = aws_ecs_task_definition.batch.family
}

output "batch_subnets" {
  value = data.aws_subnets.default.ids
}

output "batch_security_group" {
  value = aws_security_group.batch_tasks.id
}

output "run_task_example" {
  description = "Run a batch sub-command (migrate | ingest | export | test)"
  value = join(" ", [
    "aws ecs run-task --cluster ${aws_ecs_cluster.batch.name}",
    "--task-definition ${aws_ecs_task_definition.batch.family}",
    "--launch-type FARGATE --region ${var.region}",
    "--network-configuration 'awsvpcConfiguration={subnets=[${join(",", data.aws_subnets.default.ids)}],securityGroups=[${aws_security_group.batch_tasks.id}],assignPublicIp=ENABLED}'",
    "--overrides '{\"containerOverrides\":[{\"name\":\"app\",\"command\":[\"migrate\"]}]}'",
  ])
}

output "bastion_instance_id" {
  value = var.create_bastion ? aws_instance.bastion[0].id : null
}

output "ssm_port_forward_example" {
  description = "Tunnel localhost:5432 -> RDS through the bastion"
  value = var.create_bastion ? join(" ", [
    "aws ssm start-session --region ${var.region}",
    "--target ${aws_instance.bastion[0].id}",
    "--document-name AWS-StartPortForwardingSessionToRemoteHost",
    "--parameters '{\"host\":[\"${aws_db_instance.main.address}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5432\"]}'",
  ]) : null
}

output "deployer_policy_arn" {
  value = aws_iam_policy.deployer.arn
}

output "codebuild_project" {
  value = aws_codebuild_project.image.name
}

output "build_bucket" {
  value = aws_s3_bucket.build.bucket
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN secret in the GitHub repo"
  value       = var.github_repo == "" ? null : aws_iam_role.github_deploy[0].arn
}
