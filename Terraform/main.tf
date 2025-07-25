provider "aws" {
  region = "eu-central-1"
}

# ========== VARIABILE ==========
variable "client_id" {}
variable "client_secret" {}
variable "refresh_token" {}

# ========== DYNAMODB TABLE ==========
resource "aws_dynamodb_table" "activities" {
  name           = "strava_activities"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "strava_id"

  attribute {
    name = "strava_id"
    type = "S"
  }

  tags = {
    Name = "strava_activities"
  }
}

# ========== IAM LAMBDA ROLE ==========
resource "aws_iam_role" "lambda_exec" {
  name = "lambda_exec_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ========== LAMBDA DYNAMODB POLICY ==========
resource "aws_iam_policy" "lambda_dynamodb_policy" {
  name = "lambda-dynamodb-access"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Scan"
        ],
        Resource = aws_dynamodb_table.activities.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_dynamodb_attach" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_dynamodb_policy.arn
}

# ========== LAMBDA FUNCTION ==========
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
      TABLE_NAME    = aws_dynamodb_table.activities.name
      STREAMS_BUCKET = aws_s3_bucket.strava_streams.bucket
    }
  }
}

# ========== API GATEWAY ==========
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

resource "aws_apigatewayv2_route" "get_activity_route" {
  api_id    = aws_apigatewayv2_api.strava_api.id
  route_key = "GET /activities/{id}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_route" "get_activities_route" {
  api_id    = aws_apigatewayv2_api.strava_api.id
  route_key = "GET /activities"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_deployment" "strava_deployment" {
  api_id      = aws_apigatewayv2_api.strava_api.id
  description = "force redeploy-${timestamp()}"
  depends_on  = [
    aws_apigatewayv2_route.strava_route,
    aws_apigatewayv2_route.get_activity_route  # adaugat
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

resource "aws_s3_bucket" "strava_streams" {
  bucket         = "strava-activity-streams-prod"
  force_destroy  = true
}

resource "aws_iam_policy" "lambda_s3_put_streams" {
  name   = "lambda-s3-streams-access"
  path   = "/"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect   = "Allow",
      Action   = ["s3:PutObject", "s3:GetObject"],
      Resource = "${aws_s3_bucket.strava_streams.arn}/*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_s3_permission" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_s3_put_streams.arn
}


resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "ui_bucket" {
  bucket        = "strava-ui-${random_id.suffix.hex}"
  force_destroy = true

  tags = {
    Name = "StravaUI"
  }
}

resource "aws_s3_bucket_website_configuration" "ui_bucket_website" {
  bucket = aws_s3_bucket.ui_bucket.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "error.html"
  }
}

resource "aws_s3_bucket_policy" "public_ui_policy" {
  bucket = aws_s3_bucket.ui_bucket.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Sid       = "PublicReadGetObject",
      Effect    = "Allow",
      Principal = "*",
      Action    = "s3:GetObject",
      Resource  = "${aws_s3_bucket.ui_bucket.arn}/*"
    }]
  })
}
