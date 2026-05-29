import json
from unittest.mock import patch

import handler


def event(body):
    return {"httpMethod": "POST", "body": json.dumps(body)}


def test_options_preflight_returns_200():
    response = handler.lambda_handler({"httpMethod": "OPTIONS"}, {})
    assert response["statusCode"] == 200


def test_invalid_json_returns_400():
    response = handler.lambda_handler({"httpMethod": "POST", "body": "not json"}, {})
    assert response["statusCode"] == 400
    assert "invalid_json" in response["body"]


def test_missing_name_returns_400():
    response = handler.lambda_handler(event({"email": "a@b.com", "message": "Hi"}), {})
    assert response["statusCode"] == 400
    assert "missing_fields" in response["body"]


def test_missing_email_returns_400():
    response = handler.lambda_handler(event({"name": "Marcel", "message": "Hi"}), {})
    assert response["statusCode"] == 400
    assert "missing_fields" in response["body"]


def test_missing_message_returns_400():
    response = handler.lambda_handler(event({"name": "Marcel", "email": "a@b.com"}), {})
    assert response["statusCode"] == 400
    assert "missing_fields" in response["body"]


def test_invalid_email_returns_400():
    response = handler.lambda_handler(event({"name": "Marcel", "email": "notanemail", "message": "Hi"}), {})
    assert response["statusCode"] == 400
    assert "invalid_email" in response["body"]


def test_invalid_email_missing_tld_returns_400():
    response = handler.lambda_handler(event({"name": "Marcel", "email": "a@b", "message": "Hi"}), {})
    assert response["statusCode"] == 400
    assert "invalid_email" in response["body"]


@patch.object(handler, "ses")
def test_valid_request_sends_email_and_returns_200(mock_ses):
    response = handler.lambda_handler(
        event({"name": "Marcel", "email": "m@example.com", "message": "Hello!"}), {}
    )
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"ok": True}
    mock_ses.send_email.assert_called_once()


@patch.object(handler, "ses")
def test_email_is_sent_with_correct_recipient_and_reply_to(mock_ses):
    handler.lambda_handler(
        event({"name": "Marcel", "email": "m@example.com", "message": "Hello!"}), {}
    )
    kwargs = mock_ses.send_email.call_args[1]
    assert kwargs["Destination"]["ToAddresses"] == ["to@example.com"]
    assert kwargs["ReplyToAddresses"] == ["m@example.com"]
    assert "Marcel" in kwargs["Message"]["Subject"]["Data"]


@patch.object(handler, "ses")
def test_email_body_contains_name_email_and_message(mock_ses):
    handler.lambda_handler(
        event({"name": "Marcel", "email": "m@example.com", "message": "Hello!"}), {}
    )
    body = mock_ses.send_email.call_args[1]["Message"]["Body"]["Text"]["Data"]
    assert "Marcel" in body
    assert "m@example.com" in body
    assert "Hello!" in body
