# Random master password — never checked in, only ever in state + Secrets Manager.
# special = false keeps the connection URL trivially safe; db_client also
# quote_plus-es every component.
resource "random_password" "db" {
  length  = 40
  special = false
}

resource "aws_secretsmanager_secret" "db" {
  name        = "${local.name}/db"
  description = "basketball-analytics Postgres connection"
}

# db_client.py reads this JSON when DB_SECRET_ARN points at it.
resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    engine               = "postgres"
    host                 = aws_db_instance.main.address
    port                 = aws_db_instance.main.port
    dbname               = var.db_name
    username             = var.db_username
    password             = random_password.db.result
    dbInstanceIdentifier = aws_db_instance.main.identifier
  })
}
