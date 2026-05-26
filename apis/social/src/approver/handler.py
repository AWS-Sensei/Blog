import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import boto3

TABLE_NAME = os.environ["TABLE_NAME"]
LINKEDIN_SECRET_NAME = os.environ["LINKEDIN_SECRET_NAME"]

dynamodb = boto3.resource("dynamodb")
secrets = boto3.client("secretsmanager")


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
        post_url = item.get("postUrl", "https://www.linkedin.com/")
        return html_response(200, f'<h1>Already posted</h1><p><a href="{post_url}">View on LinkedIn</a></p>')

    # Claim the post before calling LinkedIn — only one concurrent Lambda wins
    try:
        table.update_item(
            Key={"postId": post_id},
            UpdateExpression="SET #s = :publishing",
            ConditionExpression="#s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":publishing": "publishing", ":pending": "pending"},
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return html_response(200, "<h1>Already posted or in progress</h1>")

    secret = json.loads(secrets.get_secret_value(SecretId=LINKEDIN_SECRET_NAME)["SecretString"])
    access_token = secret["access_token"]
    person_id = secret["person_id"]

    post_url = post_to_linkedin(access_token, person_id, item["content"])

    table.update_item(
        Key={"postId": post_id},
        UpdateExpression="SET #s = :s, postUrl = :url",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "sent", ":url": post_url},
    )

    return html_response(200, f"""
      <h1 style="color:#0077b5;">Posted to LinkedIn!</h1>
      <p>Your post is now live.</p>
      <a href="{post_url}" target="_blank"
         style="display:inline-block;background:#0077b5;color:white;
                padding:12px 24px;text-decoration:none;border-radius:6px;">
        View post on LinkedIn
      </a>
    """)


def post_to_linkedin(access_token, person_id, content):
    payload = json.dumps({
        "author": f"urn:li:person:{person_id}",
        "commentary": content,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }).encode("utf-8")

    req = Request(
        "https://api.linkedin.com/rest/posts",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202401",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )

    try:
        with urlopen(req) as response:
            urn = response.headers.get("x-restli-id", "")
    except HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"LinkedIn API error {e.code}: {body}") from e

    if urn.startswith("urn:li:share:"):
        share_id = urn.split(":")[-1]
        return f"https://www.linkedin.com/feed/update/urn:li:share:{share_id}/"
    return "https://www.linkedin.com/"


def html_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": f'<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;">{body}</body></html>',
    }
