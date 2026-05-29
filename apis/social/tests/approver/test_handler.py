import json
import sys
from unittest.mock import patch, MagicMock

handler = sys.modules["social_approver_handler"]

PENDING_ITEM = {
    "postId": "abc123",
    "status": "pending",
    "content": "Post content here",
    "articleUrl": "https://aws-sensei.cloud/posts/my-article/",
}

SENT_ITEM = {
    "postId": "abc123",
    "status": "sent",
    "postUrl": "https://www.linkedin.com/feed/update/urn:li:ugcPost:123/",
}

LINKEDIN_SECRET = json.dumps({"access_token": "token123", "person_id": "pid123"})


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
        result = handler.lambda_handler(make_event("unknown-id"), {})
    assert result["statusCode"] == 404


def test_already_sent_returns_200_with_view_link():
    with patch.object(handler, "dynamodb") as mock_ddb:
        mock_ddb.Table.return_value.get_item.return_value = {"Item": SENT_ITEM}
        result = handler.lambda_handler(make_event("abc123"), {})
    assert result["statusCode"] == 200
    assert SENT_ITEM["postUrl"] in result["body"]


def test_concurrent_approval_returns_200_without_posting():
    ConditionalCheckFailed = type("ConditionalCheckFailedException", (Exception,), {})
    with patch.object(handler, "dynamodb") as mock_ddb, \
         patch.object(handler, "secrets"), \
         patch.object(handler, "post_to_linkedin") as mock_post:
        mock_ddb.Table.return_value.get_item.return_value = {"Item": PENDING_ITEM}
        mock_ddb.meta.client.exceptions.ConditionalCheckFailedException = ConditionalCheckFailed
        mock_ddb.Table.return_value.update_item.side_effect = ConditionalCheckFailed("conflict")
        result = handler.lambda_handler(make_event("abc123"), {})
    assert result["statusCode"] == 200
    mock_post.assert_not_called()


def test_happy_path_claims_post_calls_linkedin_and_marks_sent():
    post_url = "https://www.linkedin.com/feed/update/urn:li:ugcPost:999/"
    with patch.object(handler, "dynamodb") as mock_ddb, \
         patch.object(handler, "secrets") as mock_secrets, \
         patch.object(handler, "post_to_linkedin", return_value=post_url) as mock_post:
        mock_ddb.Table.return_value.get_item.return_value = {"Item": PENDING_ITEM}
        mock_secrets.get_secret_value.return_value = {"SecretString": LINKEDIN_SECRET}
        result = handler.lambda_handler(make_event("abc123"), {})

    assert result["statusCode"] == 200
    assert post_url in result["body"]
    mock_post.assert_called_once_with("token123", "pid123", PENDING_ITEM["content"], PENDING_ITEM["articleUrl"])
    assert mock_ddb.Table.return_value.update_item.call_count == 2
