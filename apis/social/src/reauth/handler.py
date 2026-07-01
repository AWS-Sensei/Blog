import json
import os
from urllib.parse import urlencode

import boto3

LINKEDIN_SECRET_NAME = os.environ["LINKEDIN_SECRET_NAME"]
REDIRECT_URI = os.environ["REDIRECT_URI"]

secrets = boto3.client("secretsmanager")


def lambda_handler(event, context):
    secret = json.loads(secrets.get_secret_value(SecretId=LINKEDIN_SECRET_NAME)["SecretString"])
    client_id = secret["client_id"]

    params = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": "w_member_social",
    })

    return {
        "statusCode": 302,
        "headers": {"Location": f"https://www.linkedin.com/oauth/v2/authorization?{params}"},
        "body": "",
    }
