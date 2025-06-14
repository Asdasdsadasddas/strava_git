output "invoke_url" {
  value = "${aws_apigatewayv2_api.strava_api.api_endpoint}/webhook-strava"
}