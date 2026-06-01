import json
import os

import boto3

TABLE_NAME = os.environ["TABLE_NAME"]
ORCHESTRATOR_FUNCTION_NAME = os.environ["ORCHESTRATOR_FUNCTION_NAME"]

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda", region_name="eu-central-1")


def lambda_handler(event, context):
    params = event.get("queryStringParameters") or {}
    post_id = params.get("postId")

    if not post_id:
        return html_response(400, "<h1>Missing postId</h1>")

    table = dynamodb.Table(TABLE_NAME)
    item = table.get_item(Key={"postId": post_id}).get("Item")

    if not item:
        return html_response(404, "<h1>Post not found</h1>")

    if item["status"] == "sent":
        return html_response(400, "<h1>Already posted — cannot regenerate</h1>")

    s3_bucket = item.get("s3Bucket")
    s3_key = item.get("s3Key")

    if not s3_bucket or not s3_key:
        return html_response(400, "<h1>S3 key not stored — cannot regenerate</h1>")

    table.delete_item(Key={"postId": post_id})

    payload = {
        "Records": [{
            "Sns": {
                "Message": json.dumps({
                    "Records": [{
                        "s3": {
                            "bucket": {"name": s3_bucket},
                            "object": {"key": s3_key},
                        }
                    }]
                })
            }
        }]
    }

    lambda_client.invoke(
        FunctionName=ORCHESTRATOR_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )

    return html_response(200, """
      <h1 style="color:#0077b5;">Regenerating...</h1>
      <p>A new LinkedIn post draft is being generated. You'll receive a new approval email shortly.</p>
    """)


def html_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": f'<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;">{body}</body></html>',
    }
