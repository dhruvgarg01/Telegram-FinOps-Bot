provider "aws" {
  region = "us-east-1"
}

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

resource "aws_dynamodb_table" "crypto_portfolio" {
  name           = "finops-bot-portfolio"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "user_id"
  range_key      = "coin"

  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "coin"
    type = "S"
  }
}

resource "aws_s3_bucket" "bot_vault" {
  bucket_prefix = "finops-bot-vault-v2"
  force_destroy = true
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/package"
  output_path = "${path.module}/lambda_function.zip"
}

resource "aws_lambda_function" "telegram_bot" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "FinOpsTelegramBot"
  role             = data.aws_iam_role.lab_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 15

  environment {
    variables = {
      TELEGRAM_TOKEN = var.telegram_token
      DYNAMODB_TABLE = aws_dynamodb_table.crypto_portfolio.name
      S3_BUCKET      = aws_s3_bucket.bot_vault.id
    }
  }
}

resource "aws_apigatewayv2_api" "bot_api" {
  name          = "telegram-bot-api"
  protocol_type = "HTTP"
  target        = aws_lambda_function.telegram_bot.arn
}

resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.telegram_bot.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.bot_api.execution_arn}/*/*"
}

output "webhook_url" {
  value = aws_apigatewayv2_api.bot_api.api_endpoint
}

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.telegram_bot.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_metric_filter" "error_filter" {
  name           = "LambdaErrorFilter"
  pattern        = "{ $.level = \"ERROR\" }"
  log_group_name = aws_cloudwatch_log_group.lambda_logs.name

  metric_transformation {
    name      = "ErrorCount"
    namespace = "FinOpsBotMetrics"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "error_alarm" {
  alarm_name          = "FinOpsBot-Error-Alarm"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = aws_cloudwatch_log_metric_filter.error_filter.metric_transformation[0].name
  namespace           = aws_cloudwatch_log_metric_filter.error_filter.metric_transformation[0].namespace
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Triggers on ERROR log"
}