import json
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import boto3

LINKEDIN_SECRET_NAME = os.environ["LINKEDIN_SECRET_NAME"]
REDIRECT_URI = os.environ["REDIRECT_URI"]

secrets = boto3.client("secretsmanager")


def lambda_handler(event, context):
    params = event.get("queryStringParameters") or {}
    code = params.get("code")
    error = params.get("error")

    if error:
        description = params.get("error_description", error)
        return html_response(400, f"<h1>Autorisierung fehlgeschlagen</h1><p>{description}</p>")

    if not code:
        return html_response(400, "<h1>Kein Authorization Code erhalten</h1>")

    secret = json.loads(secrets.get_secret_value(SecretId=LINKEDIN_SECRET_NAME)["SecretString"])

    body = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": secret["client_id"],
        "client_secret": secret["client_secret"],
    }).encode("utf-8")

    req = Request(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urlopen(req) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8")
        return html_response(500, f"<h1>Token-Tausch fehlgeschlagen</h1><p>{e.code}: {error_body}</p>")

    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])).isoformat()

    secret["access_token"] = token_data["access_token"]
    secret["expires_at"] = expires_at
    secrets.put_secret_value(
        SecretId=LINKEDIN_SECRET_NAME,
        SecretString=json.dumps(secret),
    )

    expires_date = datetime.fromisoformat(expires_at).strftime("%d.%m.%Y")
    return html_response(200, f"""
        <h1 style="color:#0077b5;">Token aktualisiert</h1>
        <p>Neuer LinkedIn Access Token ist gültig bis <strong>{expires_date}</strong>.</p>
    """)


def html_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": f'<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;">{body}</body></html>',
    }
