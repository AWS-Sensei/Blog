import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote

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

    post_url = post_to_linkedin(access_token, person_id, item["content"], item.get("articleUrl"))

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


def fetch_og_image_url(article_url):
    with urlopen(article_url) as response:
        html = response.read().decode("utf-8")
    match = re.search(r'property="og:image"\s+content="([^"]+)"', html)
    if not match:
        match = re.search(r'content="([^"]+)"\s+property="og:image"', html)
    return match.group(1) if match else None


def upload_image_to_linkedin(access_token, person_id, image_url):
    register_payload = json.dumps({
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": f"urn:li:person:{person_id}",
            "serviceRelationships": [{
                "relationshipType": "OWNER",
                "identifier": "urn:li:userGeneratedContent",
            }],
        }
    }).encode("utf-8")

    req = Request(
        "https://api.linkedin.com/v2/assets?action=registerUpload",
        data=register_payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )
    with urlopen(req) as response:
        register_data = json.loads(response.read().decode("utf-8"))

    upload_url = register_data["value"]["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
    ]["uploadUrl"]
    asset_urn = register_data["value"]["asset"]

    with urlopen(image_url) as img_response:
        image_data = img_response.read()
        content_type = img_response.headers.get("Content-Type", "image/png")

    upload_req = Request(
        upload_url,
        data=image_data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": content_type,
        },
    )
    try:
        with urlopen(upload_req) as _:
            pass
    except HTTPError as e:
        if e.code not in (200, 201):
            raise

    return asset_urn


def post_to_linkedin(access_token, person_id, content, article_url=None):
    asset_urn = None
    if article_url:
        og_image_url = fetch_og_image_url(article_url)
        if og_image_url:
            asset_urn = upload_image_to_linkedin(access_token, person_id, og_image_url)

    share_content = {
        "shareCommentary": {"text": content},
        "shareMediaCategory": "IMAGE" if asset_urn else "NONE",
    }
    if asset_urn:
        share_content["media"] = [{"status": "READY", "media": asset_urn}]

    payload = json.dumps({
        "author": f"urn:li:person:{person_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": share_content,
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
        },
    }).encode("utf-8")

    req = Request(
        "https://api.linkedin.com/v2/ugcPosts",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )

    try:
        with urlopen(req) as response:
            post_urn = response.headers.get("x-restli-id", "")
    except HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"LinkedIn API error {e.code}: {body}") from e

    print(f"LinkedIn x-restli-id: {post_urn!r}")

    if article_url and post_urn:
        post_comment(access_token, person_id, post_urn, article_url)

    if post_urn.startswith("urn:li:ugcPost:"):
        return f"https://www.linkedin.com/feed/update/urn:li:ugcPost:{post_urn.split(':')[-1]}/"
    if post_urn.startswith("urn:li:share:"):
        return f"https://www.linkedin.com/feed/update/urn:li:share:{post_urn.split(':')[-1]}/"
    return "https://www.linkedin.com/"


def post_comment(access_token, person_id, post_urn, article_url):
    encoded_urn = quote(post_urn, safe="")
    payload = json.dumps({
        "actor": f"urn:li:person:{person_id}",
        "message": {"text": article_url},
    }).encode("utf-8")

    req = Request(
        f"https://api.linkedin.com/v2/socialActions/{encoded_urn}/comments",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )
    try:
        with urlopen(req) as _:
            pass
    except HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"Comment failed {e.code}: {body}")


def html_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": f'<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;">{body}</body></html>',
    }
