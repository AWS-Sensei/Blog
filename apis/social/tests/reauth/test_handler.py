import json
import sys
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch

handler = sys.modules["social_reauth_handler"]

SECRET = json.dumps({"client_id": "test-client-id", "client_secret": "test-secret"})


def test_redirects_to_linkedin():
    with patch.object(handler, "secrets") as mock_secrets:
        mock_secrets.get_secret_value.return_value = {"SecretString": SECRET}
        result = handler.lambda_handler({}, {})

    assert result["statusCode"] == 302
    location = result["headers"]["Location"]
    assert location.startswith("https://www.linkedin.com/oauth/v2/authorization")


def test_redirect_contains_client_id():
    with patch.object(handler, "secrets") as mock_secrets:
        mock_secrets.get_secret_value.return_value = {"SecretString": SECRET}
        result = handler.lambda_handler({}, {})

    params = parse_qs(urlparse(result["headers"]["Location"]).query)
    assert params["client_id"] == ["test-client-id"]


def test_redirect_contains_correct_redirect_uri():
    with patch.object(handler, "secrets") as mock_secrets:
        mock_secrets.get_secret_value.return_value = {"SecretString": SECRET}
        result = handler.lambda_handler({}, {})

    params = parse_qs(urlparse(result["headers"]["Location"]).query)
    assert params["redirect_uri"] == ["https://social.aws-sensei.cloud/linkedin/callback"]


def test_redirect_requests_w_member_social_scope():
    with patch.object(handler, "secrets") as mock_secrets:
        mock_secrets.get_secret_value.return_value = {"SecretString": SECRET}
        result = handler.lambda_handler({}, {})

    params = parse_qs(urlparse(result["headers"]["Location"]).query)
    assert params["scope"] == ["w_member_social"]
