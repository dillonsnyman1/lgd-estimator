# Infrastructure

Terraform for the AWS deployment: CloudFront + S3 (frontend), API Gateway +
Lambda container image (backend, arm64), ECR (backend image registry).

## Layout

- `bootstrap/` - one-time, manually-applied config that creates the
  prerequisites this config can't create for itself: the S3 bucket and
  DynamoDB table used as remote state backend, and the IAM role the
  `ci-cd.yml` workflow assumes via GitHub Actions OIDC. Already applied for
  this repo; only needs re-running if those resources are ever destroyed.
- everything else (`main.tf`, `backend.tf`, `frontend.tf`, `variables.tf`,
  `outputs.tf`) - the actual application infrastructure, applied on every
  push to `main` by the deploy job in
  [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml).

## Remote state

`main.tf` declares `backend "s3" {}` with the bucket/key/region/dynamodb_table
left blank, since the bootstrap-generated bucket name is randomized and isn't
hardcoded here. Supply them at `terraform init` time:

```bash
terraform init \
  -backend-config="bucket=<state_bucket_name from bootstrap output>" \
  -backend-config="key=lgd-estimator/terraform.tfstate" \
  -backend-config="region=eu-west-2" \
  -backend-config="dynamodb_table=<lock_table_name from bootstrap output>"
```

The CI/CD workflow does this automatically using the `TF_STATE_BUCKET` and
`TF_LOCK_TABLE` repo variables (set from the bootstrap outputs).

## The ECR/Lambda ordering problem

`aws_lambda_function.api` references an image tag in the ECR repo that this
same config creates, so a single `terraform apply` fails on a first run
before any image has been pushed. The deploy job works around this by
applying just the ECR repository first (`-target=aws_ecr_repository.backend`),
pushing the image, then running a full apply.

## Manual apply (local)

```bash
cd infra
terraform init -backend-config=... # see above
terraform apply -var lambda_image_tag=<tag already pushed to ECR>
```

Requires AWS credentials with the same permissions as the
`lgd-estimator-github-actions-deploy` role (see `bootstrap/main.tf`).
