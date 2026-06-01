import json
import sys
from unittest.mock import patch, MagicMock

handler = sys.modules["social_orchestrator_handler"]

ARTICLE_CONTENT = """---
title: Test Article
description: A test article
socialmedia: true
tags: [AWS, Lambda]
---

This is the article body.
"""

ARTICLE_CONTENT_NO_SOCIAL = """---
title: Test Article
socialmedia: false
---

Body.
"""


def make_sns_event(bucket, key):
    return {
        "Records": [{
            "Sns": {
                "Message": json.dumps({
                    "Records": [{
                        "s3": {
                            "bucket": {"name": bucket},
                            "object": {"key": key},
                        }
                    }]
                })
            }
        }]
    }


def make_s3_mock(content=ARTICLE_CONTENT):
    mock_body = MagicMock()
    mock_body.read.return_value = content.encode("utf-8")
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": mock_body}
    return mock_s3


def make_bedrock_mock():
    mock_response_body = MagicMock()
    mock_response_body.read.return_value = json.dumps({
        "content": [{"text": "Generated LinkedIn post text"}]
    }).encode()
    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {"body": mock_response_body}
    return mock_bedrock


def test_skips_file_with_unknown_language():
    with patch.object(handler, "s3", make_s3_mock()), \
         patch.object(handler, "bedrock", make_bedrock_mock()), \
         patch.object(handler, "ses") as mock_ses, \
         patch.object(handler, "dynamodb") as mock_ddb:
        handler.lambda_handler(
            make_sns_event("bucket", "_content/posts/my-slug/index.unknown.hash"), {}
        )
    mock_ddb.Table.return_value.put_item.assert_not_called()
    mock_ses.send_email.assert_not_called()


def test_skips_if_socialmedia_not_true():
    with patch.object(handler, "s3", make_s3_mock(ARTICLE_CONTENT_NO_SOCIAL)), \
         patch.object(handler, "bedrock", make_bedrock_mock()), \
         patch.object(handler, "ses") as mock_ses, \
         patch.object(handler, "dynamodb") as mock_ddb:
        handler.lambda_handler(
            make_sns_event("bucket", "_content/posts/my-slug/index.en.hash"), {}
        )
    mock_ddb.Table.return_value.put_item.assert_not_called()
    mock_ses.send_email.assert_not_called()


def test_happy_path_creates_pending_post_and_sends_approval_email():
    with patch.object(handler, "s3", make_s3_mock()), \
         patch.object(handler, "bedrock", make_bedrock_mock()), \
         patch.object(handler, "ses") as mock_ses, \
         patch.object(handler, "dynamodb") as mock_ddb:
        handler.lambda_handler(
            make_sns_event("bucket", "_content/posts/my-slug/index.en.hash"), {}
        )

    item = mock_ddb.Table.return_value.put_item.call_args[1]["Item"]
    assert item["status"] == "pending"
    assert item["slug"] == "my-slug"
    assert item["platform"] == "linkedin"
    assert item["s3Bucket"] == "bucket"
    assert item["s3Key"] == "_content/posts/my-slug/index.en.hash"
    mock_ses.send_email.assert_called_once()


def test_approval_email_contains_approve_and_retry_links():
    with patch.object(handler, "s3", make_s3_mock()), \
         patch.object(handler, "bedrock", make_bedrock_mock()), \
         patch.object(handler, "ses") as mock_ses, \
         patch.object(handler, "dynamodb"):
        handler.lambda_handler(
            make_sns_event("bucket", "_content/posts/my-slug/index.en.hash"), {}
        )

    email_html = mock_ses.send_email.call_args[1]["Message"]["Body"]["Html"]["Data"]
    assert "https://example.com/approve" in email_html
    assert "https://example.com/retry" in email_html
    assert "Regenerate" in email_html


def test_german_post_uses_de_url():
    with patch.object(handler, "s3", make_s3_mock()), \
         patch.object(handler, "bedrock", make_bedrock_mock()), \
         patch.object(handler, "ses"), \
         patch.object(handler, "dynamodb") as mock_ddb:
        handler.lambda_handler(
            make_sns_event("bucket", "_content/posts/my-slug/index.de.hash"), {}
        )

    item = mock_ddb.Table.return_value.put_item.call_args[1]["Item"]
    assert item["articleUrl"] == "https://aws-sensei.cloud/de/posts/my-slug/"


def test_duplicate_sns_delivery_is_skipped():
    ConditionalCheckFailed = type("ConditionalCheckFailedException", (Exception,), {})
    with patch.object(handler, "s3", make_s3_mock()), \
         patch.object(handler, "bedrock", make_bedrock_mock()), \
         patch.object(handler, "ses") as mock_ses, \
         patch.object(handler, "dynamodb") as mock_ddb:
        mock_ddb.meta.client.exceptions.ConditionalCheckFailedException = ConditionalCheckFailed
        mock_ddb.Table.return_value.put_item.side_effect = ConditionalCheckFailed("duplicate")
        handler.lambda_handler(
            make_sns_event("bucket", "_content/posts/my-slug/index.en.hash"), {}
        )
    mock_ses.send_email.assert_not_called()


def test_parse_frontmatter_extracts_boolean_and_string_fields():
    content = "---\ntitle: My Post\nsocialmedia: true\ndraft: false\n---\nBody"
    fm, body = handler.parse_frontmatter(content)
    assert fm["title"] == "My Post"
    assert fm["socialmedia"] is True
    assert fm["draft"] is False
    assert body == "Body"


def test_parse_frontmatter_without_delimiters_returns_empty_dict():
    content = "Just plain content without frontmatter"
    fm, body = handler.parse_frontmatter(content)
    assert fm == {}
    assert body == content
