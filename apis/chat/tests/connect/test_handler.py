import sys
import time
from unittest.mock import patch

handler = sys.modules["chat_connect_handler"]


def make_event(connection_id="conn-123", post_slug=None):
    event = {"requestContext": {"connectionId": connection_id}}
    if post_slug is not None:
        event["queryStringParameters"] = {"postSlug": post_slug}
    return event


def test_stores_connection_with_correct_fields():
    with patch.object(handler, "connections") as mock_table:
        handler.lambda_handler(make_event("conn-abc", "my-post"), {})
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["connectionId"] == "conn-abc"
        assert item["postSlug"] == "my-post"


def test_default_post_slug_is_global():
    with patch.object(handler, "connections") as mock_table:
        handler.lambda_handler(make_event(), {})
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["postSlug"] == "global"


def test_ttl_is_approximately_one_day():
    with patch.object(handler, "connections") as mock_table:
        before = int(time.time())
        handler.lambda_handler(make_event(), {})
        after = int(time.time())
        item = mock_table.put_item.call_args[1]["Item"]
        assert before + 86400 <= item["ttl"] <= after + 86400


def test_returns_200():
    with patch.object(handler, "connections"):
        result = handler.lambda_handler(make_event(), {})
        assert result["statusCode"] == 200
