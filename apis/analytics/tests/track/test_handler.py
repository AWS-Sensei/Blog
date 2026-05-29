import json
import sys
from unittest.mock import patch

handler = sys.modules["analytics_track_handler"]


def make_event(page="/", ua="Mozilla/5.0", body_extra=None):
    body = {"page": page}
    if body_extra:
        body.update(body_extra)
    return {
        "headers": {"user-agent": ua},
        "body": json.dumps(body),
    }


def test_valid_page_view_calls_firehose_and_returns_204():
    with patch.object(handler, "_firehose") as mock_fh:
        result = handler.lambda_handler(make_event("/posts/my-article"), {})
    assert result["statusCode"] == 204
    mock_fh.put_record.assert_called_once()


def test_invalid_json_returns_400():
    event = {"headers": {"user-agent": "Mozilla"}, "body": "not-json"}
    result = handler.lambda_handler(event, {})
    assert result["statusCode"] == 400


def test_page_missing_leading_slash_returns_400():
    with patch.object(handler, "_firehose"):
        result = handler.lambda_handler(make_event("posts/no-slash"), {})
    assert result["statusCode"] == 400


def test_bot_user_agent_returns_204_without_calling_firehose():
    with patch.object(handler, "_firehose") as mock_fh:
        result = handler.lambda_handler(make_event("/", ua="Googlebot/2.1 (+http://www.google.com/bot.html)"), {})
    assert result["statusCode"] == 204
    mock_fh.put_record.assert_not_called()


def test_query_string_stripped_from_page():
    with patch.object(handler, "_firehose") as mock_fh:
        handler.lambda_handler(make_event("/posts/article?utm_source=twitter#section"), {})
    record = json.loads(mock_fh.put_record.call_args[1]["Record"]["Data"])
    assert record["page"] == "/posts/article"


def test_own_domain_referrer_excluded():
    with patch.object(handler, "_firehose") as mock_fh:
        handler.lambda_handler(make_event("/", body_extra={"referrer": "https://aws-sensei.cloud/posts/x"}), {})
    record = json.loads(mock_fh.put_record.call_args[1]["Record"]["Data"])
    assert record["referrer_domain"] == ""


def test_external_referrer_domain_extracted():
    with patch.object(handler, "_firehose") as mock_fh:
        handler.lambda_handler(make_event("/", body_extra={"referrer": "https://linkedin.com/posts/123"}), {})
    record = json.loads(mock_fh.put_record.call_args[1]["Record"]["Data"])
    assert record["referrer_domain"] == "linkedin.com"


def test_is_bot_detects_known_keywords():
    assert handler._is_bot("Mozilla/5.0 (compatible; Googlebot/2.1)") is True
    assert handler._is_bot("Mozilla/5.0 (compatible; bingbot/2.0)") is True
    assert handler._is_bot("Mozilla/5.0 Chrome/120") is False


def test_parse_browser_identifies_known_browsers():
    assert handler._parse_browser("Mozilla/5.0 Chrome/120.0") == "Chrome"
    assert handler._parse_browser("Mozilla/5.0 Firefox/119.0") == "Firefox"
    assert handler._parse_browser("Mozilla/5.0 Edg/120.0") == "Edge"
    assert handler._parse_browser("curl/7.88") == "Other"
