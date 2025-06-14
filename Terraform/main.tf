provider "aws" {
  region = "eu-central-1"
}

variable "client_id" {}
variable "client_secret" {}
variable "refresh_token" {}

resource "aws_iam_role" "lambda_exec" {
  name = "lambda_exec_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "webhook_handler" {
  filename         = "${path.module}/../lambda/lambda.zip"
  function_name    = "strava_webhook_lambda"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  source_code_hash = filebase64sha256("${path.module}/../lambda/lambda.zip")
  environment {
    variables = {
      CLIENT_ID     = var.client_id
      CLIENT_SECRET = var.client_secret
      REFRESH_TOKEN = var.refresh_token
    }
  }
}


resource "aws_apigatewayv2_api" "strava_api" {
  name          = "strava-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id                 = aws_apigatewayv2_api.strava_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.webhook_handler.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "strava_route" {
  api_id    = aws_apigatewayv2_api.strava_api.id
  route_key = "ANY /webhook-strava"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_deployment" "strava_deployment" {
  api_id     = aws_apigatewayv2_api.strava_api.id
  description = "force redeploy-${timestamp()}"  # 👈 Asta forțează recreare

  depends_on = [
    aws_apigatewayv2_route.strava_route
  ]
}

resource "aws_apigatewayv2_stage" "default_stage" {
  api_id        = aws_apigatewayv2_api.strava_api.id
  name          = "prod"
  deployment_id = aws_apigatewayv2_deployment.strava_deployment.id
  auto_deploy   = false
}

resource "aws_lambda_permission" "apigw_lambda" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.strava_api.execution_arn}/*/*"
}
