import json
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

handler = sys.modules["social_expiry_checker_handler"]


def make_secret(expires_at=None):
    secret = {"access_token": "token123", "person_id": "pid123"}
    if expires_at is not None:
        secret["expires_at"] = expires_at.isoformat()
    return json.dumps(secret)


def test_no_expires_at_sends_alert():
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "ses") as mock_ses:
        mock_secrets.get_secret_value.return_value = {"SecretString": make_secret()}
        handler.lambda_handler({}, {})

    mock_ses.send_email.assert_called_once()


def test_token_expiring_in_7_days_sends_alert():
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "ses") as mock_ses:
        mock_secrets.get_secret_value.return_value = {"SecretString": make_secret(expires_at)}
        handler.lambda_handler({}, {})

    mock_ses.send_email.assert_called_once()


def test_token_expiring_in_13_days_sends_alert():
    expires_at = datetime.now(timezone.utc) + timedelta(days=13)
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "ses") as mock_ses:
        mock_secrets.get_secret_value.return_value = {"SecretString": make_secret(expires_at)}
        handler.lambda_handler({}, {})

    mock_ses.send_email.assert_called_once()


def test_token_expiring_in_30_days_sends_no_alert():
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "ses") as mock_ses:
        mock_secrets.get_secret_value.return_value = {"SecretString": make_secret(expires_at)}
        handler.lambda_handler({}, {})

    mock_ses.send_email.assert_not_called()


def test_alert_email_contains_reauth_url():
    expires_at = datetime.now(timezone.utc) + timedelta(days=5)
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "ses") as mock_ses:
        mock_secrets.get_secret_value.return_value = {"SecretString": make_secret(expires_at)}
        handler.lambda_handler({}, {})

    email_body = mock_ses.send_email.call_args.kwargs["Message"]["Body"]["Html"]["Data"]
    assert "https://social.aws-sensei.cloud/linkedin/reauth" in email_body
