output "cloudfront_domain_name" {
  description = "Public URL of the dashboard (live demo)."
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "api_gateway_invoke_url" {
  description = "Base URL of the API - set as VITE_API_BASE_URL when building the frontend."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "ecr_repository_url" {
  description = "ECR repository the deploy workflow pushes the backend image to."
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_bucket_name" {
  description = "S3 bucket the deploy workflow syncs the built frontend to."
  value       = aws_s3_bucket.frontend.bucket
}

output "lambda_function_name" {
  description = "Lambda function the deploy workflow updates with the new image."
  value       = aws_lambda_function.api.function_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID, used to create cache invalidations after a frontend deploy."
  value       = aws_cloudfront_distribution.frontend.id
}
