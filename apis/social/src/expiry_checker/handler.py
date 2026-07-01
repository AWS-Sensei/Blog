import json
import os
from datetime import datetime, timezone

import boto3

LINKEDIN_SECRET_NAME = os.environ["LINKEDIN_SECRET_NAME"]
FROM_EMAIL = os.environ["FROM_EMAIL"]
TO_EMAIL = os.environ["TO_EMAIL"]
REAUTH_URL = os.environ["REAUTH_URL"]
WARNING_DAYS = 14

secrets = boto3.client("secretsmanager")
ses = boto3.client("ses", region_name="eu-central-1")


def lambda_handler(event, context):
    secret = json.loads(secrets.get_secret_value(SecretId=LINKEDIN_SECRET_NAME)["SecretString"])
    expires_at_str = secret.get("expires_at")

    if not expires_at_str:
        send_alert("unbekannt", None)
        return

    expires_at = datetime.fromisoformat(expires_at_str)
    days_left = (expires_at - datetime.now(timezone.utc)).days

    if days_left < WARNING_DAYS:
        send_alert(expires_at.strftime("%d.%m.%Y"), days_left)
        print(f"Alert sent: token expires in {days_left} days")
    else:
        print(f"Token OK: {days_left} days remaining")


def send_alert(expires_date, days_left):
    days_text = f"noch {days_left} Tage" if days_left is not None else "Ablaufdatum unbekannt"

    ses.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": [TO_EMAIL]},
        Message={
            "Subject": {"Data": f"LinkedIn Token erneuern ({days_text})"},
            "Body": {
                "Html": {
                    "Data": f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:600px;margin:40px auto;color:#1a1a1a;">
  <h2 style="color:#0077b5;">LinkedIn Token erneuern</h2>
  <p>Dein LinkedIn Access Token läuft am <strong>{expires_date}</strong> ab ({days_text}).</p>
  <p>Klick auf den Button, logge dich bei LinkedIn ein — fertig.</p>
  <a href="{REAUTH_URL}"
     style="display:inline-block;background:#0077b5;color:white;
            padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">
    Token erneuern
  </a>
</body>
</html>"""
                }
            },
        },
    )
