import json
import os
import uuid
import boto3
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
connections = dynamodb.Table(os.environ["CONNECTIONS_TABLE"])
messages = dynamodb.Table(os.environ["MESSAGES_TABLE"])


def lambda_handler(event, context):
    domain = event["requestContext"]["domainName"]
    stage = event["requestContext"]["stage"]
    sender_id = event["requestContext"]["connectionId"]

    body = json.loads(event.get("body") or "{}")
    post_slug = body.get("postSlug", "global")
    author = body.get("author", "Anonymous")[:50].strip()
    text = body.get("message", "").strip()[:500]

    if not text or not author:
        return {"statusCode": 400}

    timestamp = datetime.now(timezone.utc).isoformat()
    sort_key = f"{timestamp}#{str(uuid.uuid4())[:8]}"

    message = {
        "postSlug": post_slug,
        "sortKey": sort_key,
        "author": author,
        "message": text,
        "createdAt": timestamp,
    }
    messages.put_item(Item=message)

    api_client = boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=f"https://{domain}/{stage}",
    )
    payload = json.dumps({"type": "message", "message": message}).encode()

    all_connections = connections.scan(
        FilterExpression=Attr("postSlug").eq(post_slug)
    )

    stale = []
    for conn in all_connections["Items"]:
        try:
            api_client.post_to_connection(ConnectionId=conn["connectionId"], Data=payload)
        except api_client.exceptions.GoneException:
            stale.append(conn["connectionId"])

    for conn_id in stale:
        connections.delete_item(Key={"connectionId": conn_id})

    return {"statusCode": 200}
