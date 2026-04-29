import json
import os
import re
import boto3

ses = boto3.client("ses", region_name="eu-central-1")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://aws-sensei.cloud",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

TO_EMAIL = os.environ["TO_EMAIL"]
FROM_EMAIL = os.environ["FROM_EMAIL"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return error(400, "invalid_json")

    name = body.get("name", "").strip()[:100]
    email = body.get("email", "").strip()[:200]
    message = body.get("message", "").strip()[:2000]

    if not name or not email or not message:
        return error(400, "missing_fields")

    if not EMAIL_RE.match(email):
        return error(400, "invalid_email")

    ses.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": [TO_EMAIL]},
        ReplyToAddresses=[email],
        Message={
            "Subject": {"Data": f"Blog contact from {name}"},
            "Body": {
                "Text": {
                    "Data": f"Name: {name}\nE-Mail: {email}\n\n{message}"
                }
            },
        },
    )

    return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps({"ok": True})}


def error(status, code):
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": code}),
    }
