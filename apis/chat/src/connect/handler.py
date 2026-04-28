import os
import time
import boto3

dynamodb = boto3.resource("dynamodb")
connections = dynamodb.Table(os.environ["CONNECTIONS_TABLE"])


def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    post_slug = (event.get("queryStringParameters") or {}).get("postSlug", "global")

    connections.put_item(Item={
        "connectionId": connection_id,
        "postSlug": post_slug,
        "ttl": int(time.time()) + 86400,
    })

    return {"statusCode": 200}
