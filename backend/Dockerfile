# Lambda container image for the FastAPI backend, built for arm64
# (Graviton) and run via Mangum (see app/main.py). Pushed to ECR and
# referenced by the Lambda function in infra/backend.tf.
FROM public.ecr.aws/lambda/python:3.13

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ${LAMBDA_TASK_ROOT}/app

CMD ["app.main.handler"]
