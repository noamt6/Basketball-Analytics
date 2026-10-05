# ---------------------------------------------------------------------------
# Serverless GenAI insights pipeline (daily).
#
#   EventBridge cron 06:00 UTC -> Lambda (python3.12, arm64, NO VPC)
#     reads   s3://<site bucket>/data.json
#     calls   Bedrock Converse (Amazon Nova Lite via the EU inference profile;
#             swap to eu.anthropic.claude-haiku-4-5-* once the account's
#             Anthropic "use case details" form is submitted)
#     writes  s3://<site bucket>/insights.json
#     runs    cloudfront:CreateInvalidation for /insights.json
#
# No VPC config -> no ENI in the VPC -> no NAT gateway and no paid interface
# endpoints. S3 / Bedrock / CloudFront are reached over public AWS endpoints.
#
# The live resources were first created by scripts/deploy_genai_insights.py;
# this file is the Terraform equivalent for parity and is not wired into main
# apply yet (import before enabling to avoid a name clash).
# ---------------------------------------------------------------------------

locals {
  genai_fn_name    = "${local.name}-genai-insights"
  genai_model_id   = "eu.amazon.nova-lite-v1:0"
  genai_schedule   = "cron(0 6 * * ? *)"
  genai_source_dir = "${path.module}/../lambda/genai_insights"
}

data "archive_file" "genai_insights" {
  type        = "zip"
  source_file = "${local.genai_source_dir}/lambda_function.py"
  output_path = "${path.module}/.build/genai_insights.zip"
}

resource "aws_iam_role" "genai_insights" {
  name = "${local.genai_fn_name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "genai_insights_basic" {
  role       = aws_iam_role.genai_insights.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "genai_insights" {
  name = "${local.name}-genai-insights"
  role = aws_iam_role.genai_insights.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadData"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.site.arn}/data.json"
      },
      {
        Sid      = "WriteInsights"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.site.arn}/insights.json"
      },
      {
        Sid    = "InvokeBedrock"
        Effect = "Allow"
        Action = "bedrock:InvokeModel"
        Resource = [
          "arn:aws:bedrock:${var.region}:${local.account_id}:inference-profile/${local.genai_model_id}",
          "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
        ]
      },
      {
        Sid      = "InvalidateCDN"
        Effect   = "Allow"
        Action   = "cloudfront:CreateInvalidation"
        Resource = aws_cloudfront_distribution.site.arn
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "genai_insights" {
  name              = "/aws/lambda/${local.genai_fn_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "genai_insights" {
  function_name    = local.genai_fn_name
  role             = aws_iam_role.genai_insights.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "lambda_function.handler"
  filename         = data.archive_file.genai_insights.output_path
  source_code_hash = data.archive_file.genai_insights.output_base64sha256
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      SITE_BUCKET                = aws_s3_bucket.site.bucket
      DATA_KEY                   = "data.json"
      INSIGHTS_KEY               = "insights.json"
      CLOUDFRONT_DISTRIBUTION_ID = aws_cloudfront_distribution.site.id
      BEDROCK_MODEL_ID           = local.genai_model_id
      BEDROCK_REGION             = var.region
    }
  }

  depends_on = [aws_cloudwatch_log_group.genai_insights]
}

resource "aws_cloudwatch_event_rule" "genai_insights_daily" {
  name                = "${local.genai_fn_name}-daily"
  description         = "Daily GenAI insights refresh for the dashboard"
  schedule_expression = local.genai_schedule
}

resource "aws_cloudwatch_event_target" "genai_insights_daily" {
  rule = aws_cloudwatch_event_rule.genai_insights_daily.name
  arn  = aws_lambda_function.genai_insights.arn
}

resource "aws_lambda_permission" "genai_insights_events" {
  statement_id  = "events-daily-invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.genai_insights.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.genai_insights_daily.arn
}

output "genai_insights_function" {
  value = aws_lambda_function.genai_insights.function_name
}
