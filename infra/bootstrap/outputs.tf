output "state_bucket_name" {
  description = "S3 bucket holding Terraform remote state for infra/."
  value       = aws_s3_bucket.terraform_state.bucket
}

output "lock_table_name" {
  description = "DynamoDB table used for Terraform state locking."
  value       = aws_dynamodb_table.terraform_lock.name
}

output "github_actions_role_arn" {
  description = "IAM role the deploy workflow assumes via OIDC (AWS_DEPLOY_ROLE_ARN secret)."
  value       = aws_iam_role.github_actions_deploy.arn
}
