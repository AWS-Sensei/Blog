import json
import os

import boto3

CACHE_BUCKET = os.environ["CACHE_BUCKET"]
CACHE_KEY = "cache/dashboard.json"

_s3 = boto3.client("s3")


def lambda_handler(event, context):
    try:
        obj = _s3.get_object(Bucket=CACHE_BUCKET, Key=CACHE_KEY)
        body = obj["Body"].read().decode()
    except _s3.exceptions.NoSuchKey:
        return {"statusCode": 503, "body": json.dumps({"error": "cache not ready"})}

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": body,
    }
