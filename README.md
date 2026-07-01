# Serverless FinOps Telegram Bot

An enterprise-grade, serverless Telegram bot built on AWS. It tracks crypto portfolios, fetches live weather/pricing data via external APIs, and features a secure S3 file vault.

## Architecture & Infrastructure
Entirely provisioned via Infrastructure as Code (Terraform) targeting a live AWS Academy environment:
* **Compute:** AWS Lambda (Python 3.x)
* **Database:** DynamoDB (NoSQL for user portfolio persistence)
* **Storage:** Amazon S3 (Object storage for Telegram file uploads)
* **Observability:** CloudWatch Logs, Metric Filters, and SNS Alarms

## External API Integrations
* **Telegram Bot API:** Handles incoming webhooks and outgoing messages.
* **CoinGecko API:** Fetches real-time cryptocurrency pricing.
* **Open-Meteo API:** Handles geolocation and live weather forecasting.

## Prerequisites
1.  An active AWS Learner Lab session.
2.  AWS CLI configured with active temporary session credentials.
3.  Terraform installed locally.
4.  A Telegram Bot Token (from BotFather).

## Deployment Instructions (How to Deploy)
1. Initialize Terraform:
   `terraform init`
2. Package the Python Lambda code:
   `Compress-Archive -Path .\package\* -DestinationPath .\lambda_function.zip -Force`
3. Export your Telegram Token as an environment variable to keep secrets out of the code:
   `$env:TF_VAR_telegram_token="YOUR_TOKEN_HERE"`
4. Apply the infrastructure:
   `terraform apply -auto-approve`

## Cleanup Instructions (How to Destroy)
To prevent phantom charges or resource limits, tear down the infrastructure when finished:
`terraform destroy -auto-approve`

## IAM Security (Least Privilege)
This project enforces least-privilege IAM policies. The Lambda execution role (`LabRole`) is restricted to only allow `PutItem`/`GetItem`/`Query` on the specific DynamoDB table, and `PutObject`/`GetObject` on the specific S3 bucket.

## Observability Setup
Custom CloudWatch logs distinguish between user warnings (e.g., typos) and critical system faults. A CloudWatch Metric Filter (`CrashCatcher`) monitors for `CRITICAL` log strings and triggers an SNS Alarm if the system registers a failure.