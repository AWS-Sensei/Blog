import os
import boto3

dynamodb = boto3.resource("dynamodb")
connections = dynamodb.Table(os.environ["CONNECTIONS_TABLE"])


def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    connections.delete_item(Key={"connectionId": connection_id})
    return {"statusCode": 200}
