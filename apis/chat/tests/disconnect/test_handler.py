import sys
from unittest.mock import patch

handler = sys.modules["chat_disconnect_handler"]


def make_event(connection_id="conn-123"):
    return {"requestContext": {"connectionId": connection_id}}


def test_deletes_correct_connection():
    with patch.object(handler, "connections") as mock_table:
        handler.lambda_handler(make_event("conn-abc"), {})
        mock_table.delete_item.assert_called_once_with(Key={"connectionId": "conn-abc"})


def test_returns_200():
    with patch.object(handler, "connections"):
        result = handler.lambda_handler(make_event(), {})
        assert result["statusCode"] == 200
