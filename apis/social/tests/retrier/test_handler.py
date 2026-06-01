import sys
from unittest.mock import patch, MagicMock

handler = sys.modules["social_retrier_handler"]

PENDING_ITEM = {
    "postId": "abc123",
    "status": "pending",
    "s3Bucket": "my-bucket",
    "s3Key": "_content/posts/my-slug/index.en.abc",
}

SENT_ITEM = {
    "postId": "abc123",
    "status": "sent",
    "s3Bucket": "my-bucket",
    "s3Key": "_content/posts/my-slug/index.en.abc",
}


def make_event(post_id=None):
    if post_id is None:
        return {}
    return {"queryStringParameters": {"postId": post_id}}


def test_missing_post_id_returns_400():
    result = handler.lambda_handler(make_event(), {})
    assert result["statusCode"] == 400


def test_unknown_post_id_returns_404():
    with patch.object(handler, "dynamodb") as mock_ddb:
        mock_ddb.Table.return_value.get_item.return_value = {}
        result = handler.lambda_handler(make_event("unknown"), {})
    assert result["statusCode"] == 404


def test_already_sent_returns_400():
    with patch.object(handler, "dynamodb") as mock_ddb:
        mock_ddb.Table.return_value.get_item.return_value = {"Item": SENT_ITEM}
        result = handler.lambda_handler(make_event("abc123"), {})
    assert result["statusCode"] == 400
    assert "Already posted" in result["body"]


def test_missing_s3_key_returns_400():
    item_without_key = {"postId": "abc123", "status": "pending"}
    with patch.object(handler, "dynamodb") as mock_ddb:
        mock_ddb.Table.return_value.get_item.return_value = {"Item": item_without_key}
        result = handler.lambda_handler(make_event("abc123"), {})
    assert result["statusCode"] == 400
    assert "S3 key not stored" in result["body"]


def test_happy_path_deletes_item_and_invokes_orchestrator():
    with patch.object(handler, "dynamodb") as mock_ddb, \
         patch.object(handler, "lambda_client") as mock_lambda:
        mock_ddb.Table.return_value.get_item.return_value = {"Item": PENDING_ITEM}
        result = handler.lambda_handler(make_event("abc123"), {})

    assert result["statusCode"] == 200
    assert "Regenerating" in result["body"]
    mock_ddb.Table.return_value.delete_item.assert_called_once_with(Key={"postId": "abc123"})
    mock_lambda.invoke.assert_called_once()
    invoke_call = mock_lambda.invoke.call_args
    assert invoke_call.kwargs["FunctionName"] == "sensei-social-orchestrator"
    assert invoke_call.kwargs["InvocationType"] == "Event"
