import json
import sys
from unittest.mock import patch, MagicMock

handler = sys.modules["chat_message_handler"]


def make_event(body=None, connection_id="conn-123"):
    return {
        "requestContext": {
            "connectionId": connection_id,
            "domainName": "xxx.execute-api.eu-central-1.amazonaws.com",
            "stage": "prod",
        },
        "body": json.dumps(body) if body is not None else None,
    }


def make_api_client():
    client = MagicMock()
    client.exceptions.GoneException = type("GoneException", (Exception,), {})
    return client


def test_get_history_queries_messages_and_sends_response():
    api_client = make_api_client()
    items = [{"postSlug": "test", "sortKey": "a", "author": "Alice", "message": "Hi"}]
    with patch.object(handler, "messages") as mock_messages, \
         patch.object(handler, "connections"), \
         patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = api_client
        mock_messages.query.return_value = {"Items": items}
        result = handler.lambda_handler(
            make_event({"action": "getHistory", "postSlug": "my-post"}), {}
        )
    assert result["statusCode"] == 200
    mock_messages.query.assert_called_once()
    sent = json.loads(api_client.post_to_connection.call_args[1]["Data"])
    assert sent["type"] == "history"
    assert sent["messages"] == items


def test_send_message_stores_and_broadcasts_to_all_connections():
    api_client = make_api_client()
    with patch.object(handler, "messages") as mock_messages, \
         patch.object(handler, "connections") as mock_connections, \
         patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = api_client
        mock_connections.scan.return_value = {"Items": [
            {"connectionId": "conn-a"},
            {"connectionId": "conn-b"},
        ]}
        result = handler.lambda_handler(
            make_event({"author": "Alice", "message": "Hello", "postSlug": "test-post"}), {}
        )
    assert result["statusCode"] == 200
    mock_messages.put_item.assert_called_once()
    assert api_client.post_to_connection.call_count == 2


def test_empty_message_returns_400():
    api_client = make_api_client()
    with patch.object(handler, "messages"), \
         patch.object(handler, "connections"), \
         patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = api_client
        result = handler.lambda_handler(make_event({"author": "Alice", "message": ""}), {})
    assert result["statusCode"] == 400


def test_empty_author_returns_400():
    api_client = make_api_client()
    with patch.object(handler, "messages"), \
         patch.object(handler, "connections"), \
         patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = api_client
        result = handler.lambda_handler(make_event({"author": "", "message": "Hello"}), {})
    assert result["statusCode"] == 400


def test_stale_connection_is_deleted_after_gone_exception():
    GoneException = type("GoneException", (Exception,), {})
    api_client = MagicMock()
    api_client.exceptions.GoneException = GoneException
    api_client.post_to_connection.side_effect = GoneException("gone")

    with patch.object(handler, "messages"), \
         patch.object(handler, "connections") as mock_connections, \
         patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = api_client
        mock_connections.scan.return_value = {"Items": [{"connectionId": "stale-conn"}]}
        result = handler.lambda_handler(
            make_event({"author": "Alice", "message": "Hello"}), {}
        )
    assert result["statusCode"] == 200
    mock_connections.delete_item.assert_called_once_with(Key={"connectionId": "stale-conn"})


def test_default_post_slug_is_global():
    api_client = make_api_client()
    with patch.object(handler, "messages") as mock_messages, \
         patch.object(handler, "connections") as mock_connections, \
         patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = api_client
        mock_connections.scan.return_value = {"Items": []}
        handler.lambda_handler(make_event({"author": "Alice", "message": "Hi"}), {})
        item = mock_messages.put_item.call_args[1]["Item"]
        assert item["postSlug"] == "global"
