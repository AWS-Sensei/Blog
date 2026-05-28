import hashlib
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name="eu-central-1")
ses = boto3.client("ses", region_name="eu-central-1")
dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ["TABLE_NAME"]
FROM_EMAIL = os.environ["FROM_EMAIL"]
TO_EMAIL = os.environ["TO_EMAIL"]
APPROVE_URL = os.environ["APPROVE_URL"]
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]


def lambda_handler(event, context):
    for record in event["Records"]:
        message = json.loads(record["Sns"]["Message"])
        s3_record = message["Records"][0]
        bucket = s3_record["s3"]["bucket"]["name"]
        key = unquote_plus(s3_record["s3"]["object"]["key"])

        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8")

        frontmatter, body = parse_frontmatter(content)

        if ".en." not in key:
            print(f"Skipping {key}: not an English post")
            return

        if not frontmatter.get("socialmedia", False):
            print(f"Skipping {key}: socialmedia not true")
            return

        # key format: _content/posts/{slug}/index.en.{hash}
        slug = key.split("/")[2]
        title = frontmatter.get("title", slug)
        article_url = f"https://aws-sensei.cloud/posts/{slug}/"

        linkedin_post = generate_linkedin_post(frontmatter, body, article_url)

        post_id = hashlib.md5(key.encode()).hexdigest()
        try:
            dynamodb.Table(TABLE_NAME).put_item(
                Item={
                    "postId": post_id,
                    "slug": slug,
                    "platform": "linkedin",
                    "content": linkedin_post,
                    "status": "pending",
                    "articleTitle": title,
                    "articleUrl": article_url,
                    "articleDescription": frontmatter.get("description", ""),
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                },
                ConditionExpression="attribute_not_exists(postId)",
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            print(f"Duplicate SNS delivery for {key}, skipping")
            return

        send_approval_email(post_id, title, linkedin_post)
        print(f"Created pending post {post_id} for {slug}")


def parse_frontmatter(content):
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not match:
        return {}, content

    fm = {}
    for line in match.group(1).split("\n"):
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.lower() == "true":
            fm[key] = True
        elif value.lower() == "false":
            fm[key] = False
        elif value.startswith("[") and value.endswith("]"):
            fm[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
        else:
            fm[key] = value.strip("\"'")

    return fm, match.group(2)


def generate_linkedin_post(frontmatter, body, article_url):
    title = frontmatter.get("title", "")
    description = frontmatter.get("description", "")
    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    prompt = f"""You are a senior cloud engineer sharing something you built on LinkedIn. Write a short post about a new blog article — but write it like a human, not a content writer following a template.

Article title: {title}
Description: {description}
Tags: {", ".join(tags)}

Article excerpt:
{body[:3000]}

The post should read like a brief, natural update from an engineer. Pick ONE interesting aspect of the article — a surprising constraint, an unexpected tradeoff, or a design decision worth explaining — and write about that. Do not try to summarize everything. Three short paragraphs at most:

1. A single sentence or question that hooks the reader based on that one aspect.
2. Two or three sentences explaining what you built and why that aspect was interesting or tricky.
3. A short closing sentence that points to the full article at this exact URL: {article_url}

End with 3-4 relevant hashtags on a new line.

Tone: direct, technical, no hype. Write like you would in a Slack message to a smart colleague, not like a press release.

Rules: plain text only, no markdown, no asterisks, no bullet points, no headers. The output will be pasted into LinkedIn as-is.

Return only the post text, nothing else."""

    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


def send_approval_email(post_id, title, content):
    approve_link = f"{APPROVE_URL}?postId={post_id}"
    content_escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    ses.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": [TO_EMAIL]},
        Message={
            "Subject": {"Data": f"LinkedIn Post: {title}"},
            "Body": {
                "Html": {
                    "Data": f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:600px;margin:40px auto;color:#1a1a1a;">
  <h2 style="color:#0077b5;">New LinkedIn Post Ready</h2>
  <h3>{title}</h3>
  <div style="background:#f5f5f5;padding:20px;border-radius:8px;
              white-space:pre-wrap;font-size:14px;line-height:1.6;">
{content_escaped}
  </div>
  <a href="{approve_link}"
     style="display:inline-block;margin-top:24px;background:#0077b5;color:white;
            padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">
    Approve &amp; Post to LinkedIn
  </a>
</body>
</html>"""
                }
            },
        },
    )
