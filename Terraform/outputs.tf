output "invoke_url" {
  value = "${aws_apigatewayv2_api.strava_api.api_endpoint}/webhook-strava"
}

output "lambda_dynamodb_policy_arn" {
  value = aws_iam_policy.lambda_dynamodb_policy.arn
}

output "ui_url" {
  description = "URL public pentru UI-ul static"
  value       = "http://${aws_s3_bucket_website_configuration.ui_bucket_website.website_endpoint}"

}