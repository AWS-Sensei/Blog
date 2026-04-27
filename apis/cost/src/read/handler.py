import json
import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm", region_name="eu-central-1")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://aws-sensei.cloud",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        param = ssm.get_parameter(Name="/sensei/blog/cost-data")
        data = json.loads(param["Parameter"]["Value"])
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(data),
        }
    except ClientError as e:
        if e.response["Error"]["Code"] == "ParameterNotFound":
            return {
                "statusCode": 503,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "not_ready"}),
            }
        raise
