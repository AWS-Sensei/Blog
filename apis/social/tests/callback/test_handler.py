import json
import sys
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

handler = sys.modules["social_callback_handler"]

SECRET = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "access_token": "old-token",
    "person_id": "pid123",
}

TOKEN_RESPONSE = {
    "access_token": "new-token-xyz",
    "expires_in": 5184000,  # 60 days
}


def make_event(params=None):
    return {"queryStringParameters": params or {}}


def mock_urlopen_response(data: dict):
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = lambda s: s
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_ctx.read.return_value = json.dumps(data).encode("utf-8")
    return mock_ctx


def test_missing_code_returns_400():
    result = handler.lambda_handler(make_event(), {})
    assert result["statusCode"] == 400


def test_linkedin_error_param_returns_400():
    event = make_event({"error": "access_denied", "error_description": "User cancelled"})
    result = handler.lambda_handler(event, {})
    assert result["statusCode"] == 400
    assert "User cancelled" in result["body"]


def test_token_exchange_failure_returns_500():
    http_error = HTTPError("url", 400, "Bad Request", {}, BytesIO(b'{"error":"invalid_grant"}'))
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "urlopen", side_effect=http_error):
        mock_secrets.get_secret_value.return_value = {"SecretString": json.dumps(SECRET)}
        result = handler.lambda_handler(make_event({"code": "auth-code-123"}), {})

    assert result["statusCode"] == 500


def test_happy_path_returns_200_with_expiry_date():
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "urlopen", return_value=mock_urlopen_response(TOKEN_RESPONSE)):
        mock_secrets.get_secret_value.return_value = {"SecretString": json.dumps(SECRET)}
        result = handler.lambda_handler(make_event({"code": "auth-code-123"}), {})

    assert result["statusCode"] == 200
    assert "new-token-xyz" not in result["body"]  # token must not be exposed in HTML


def test_happy_path_writes_new_token_to_secrets_manager():
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "urlopen", return_value=mock_urlopen_response(TOKEN_RESPONSE)):
        mock_secrets.get_secret_value.return_value = {"SecretString": json.dumps(SECRET)}
        handler.lambda_handler(make_event({"code": "auth-code-123"}), {})

    call_args = mock_secrets.put_secret_value.call_args
    written = json.loads(call_args.kwargs["SecretString"])
    assert written["access_token"] == "new-token-xyz"
    assert "expires_at" in written


def test_happy_path_preserves_existing_secret_fields():
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "urlopen", return_value=mock_urlopen_response(TOKEN_RESPONSE)):
        mock_secrets.get_secret_value.return_value = {"SecretString": json.dumps(SECRET)}
        handler.lambda_handler(make_event({"code": "auth-code-123"}), {})

    call_args = mock_secrets.put_secret_value.call_args
    written = json.loads(call_args.kwargs["SecretString"])
    assert written["person_id"] == "pid123"
    assert written["client_id"] == "test-client-id"


def test_expires_at_is_roughly_60_days_from_now():
    with patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "urlopen", return_value=mock_urlopen_response(TOKEN_RESPONSE)):
        mock_secrets.get_secret_value.return_value = {"SecretString": json.dumps(SECRET)}
        handler.lambda_handler(make_event({"code": "auth-code-123"}), {})

    call_args = mock_secrets.put_secret_value.call_args
    written = json.loads(call_args.kwargs["SecretString"])
    expires_at = datetime.fromisoformat(written["expires_at"])
    days_until_expiry = (expires_at - datetime.now(timezone.utc)).days
    assert 58 <= days_until_expiry <= 61
