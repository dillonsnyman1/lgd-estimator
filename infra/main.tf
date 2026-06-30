# Providers and remote state backend for the application infrastructure.
#
# The S3 backend is intentionally left partially configured - bucket, key,
# region and dynamodb_table are supplied at `terraform init` time via
# -backend-config flags (see infra/README.md), so the bootstrap-created
# bucket/table names don't need to be hardcoded or committed.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
