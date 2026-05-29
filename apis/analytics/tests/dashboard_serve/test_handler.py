import json
import sys
from unittest.mock import patch, MagicMock

handler = sys.modules["analytics_dashboard_serve_handler"]


def test_returns_200_with_cached_dashboard():
    data = {"top_articles": [["/posts/x", "5"]], "daily_traffic": []}
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(data).encode()
    with patch.object(handler, "_s3") as mock_s3:
        mock_s3.get_object.return_value = {"Body": mock_body}
        result = handler.lambda_handler({}, {})
    assert result["statusCode"] == 200
    assert json.loads(result["body"]) == data


def test_returns_503_when_cache_not_ready():
    NoSuchKey = type("NoSuchKey", (Exception,), {})
    with patch.object(handler, "_s3") as mock_s3:
        mock_s3.exceptions.NoSuchKey = NoSuchKey
        mock_s3.get_object.side_effect = NoSuchKey("not found")
        result = handler.lambda_handler({}, {})
    assert result["statusCode"] == 503
