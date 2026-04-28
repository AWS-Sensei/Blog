import json
import os
import time
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
connections = dynamodb.Table(os.environ["CONNECTIONS_TABLE"])
messages = dynamodb.Table(os.environ["MESSAGES_TABLE"])


def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    post_slug = (event.get("queryStringParameters") or {}).get("postSlug", "global")

    connections.put_item(Item={
        "connectionId": connection_id,
        "postSlug": post_slug,
        "ttl": int(time.time()) + 86400,
    })

    try:
        domain = event["requestContext"]["domainName"]
        stage = event["requestContext"]["stage"]
        api_client = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=f"https://{domain}/{stage}",
        )
        result = messages.query(
            KeyConditionExpression=Key("postSlug").eq(post_slug),
            ScanIndexForward=True,
            Limit=50,
        )
        if result["Items"]:
            api_client.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps({"type": "history", "messages": result["Items"]}).encode(),
            )
    except Exception as e:
        print(f"Error sending history: {e}")

    return {"statusCode": 200}
