import json
from unittest.mock import patch

import handler

COMPREHEND_RESPONSE = {
    "Sentiment": "POSITIVE",
    "SentimentScore": {
        "Positive": 0.95,
        "Negative": 0.01,
        "Neutral": 0.03,
        "Mixed": 0.01,
    },
}


def event(text=None, lang="en"):
    body = {"lang": lang}
    if text is not None:
        body["text"] = text
    return {"httpMethod": "POST", "body": json.dumps(body)}


def test_options_preflight_returns_200():
    response = handler.lambda_handler({"httpMethod": "OPTIONS"}, {})
    assert response["statusCode"] == 200


def test_empty_text_returns_400():
    response = handler.lambda_handler(event(text=""), {})
    assert response["statusCode"] == 400
    assert "text is required" in response["body"]


def test_missing_text_returns_400():
    response = handler.lambda_handler(event(), {})
    assert response["statusCode"] == 400
    assert "text is required" in response["body"]


def test_text_exceeding_5000_chars_returns_400():
    response = handler.lambda_handler(event(text="x" * 5001), {})
    assert response["statusCode"] == 400
    assert "5000" in response["body"]


@patch.object(handler, "comprehend")
def test_valid_request_returns_sentiment_and_scores(mock_comprehend):
    mock_comprehend.detect_sentiment.return_value = COMPREHEND_RESPONSE
    response = handler.lambda_handler(event("I love this service!"), {})
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["sentiment"] == "positive"
    assert body["scores"]["positive"] == 0.95
    assert set(body["scores"].keys()) == {"positive", "negative", "neutral", "mixed"}


@patch.object(handler, "comprehend")
def test_unsupported_lang_defaults_to_en(mock_comprehend):
    mock_comprehend.detect_sentiment.return_value = COMPREHEND_RESPONSE
    handler.lambda_handler(event("hello", lang="xx"), {})
    _, kwargs = mock_comprehend.detect_sentiment.call_args
    assert kwargs["LanguageCode"] == "en"


@patch.object(handler, "comprehend")
def test_supported_lang_is_forwarded(mock_comprehend):
    mock_comprehend.detect_sentiment.return_value = COMPREHEND_RESPONSE
    handler.lambda_handler(event("Ich liebe das!", lang="de"), {})
    _, kwargs = mock_comprehend.detect_sentiment.call_args
    assert kwargs["LanguageCode"] == "de"


@patch.object(handler, "comprehend")
def test_comprehend_exception_returns_500(mock_comprehend):
    mock_comprehend.detect_sentiment.side_effect = Exception("service unavailable")
    response = handler.lambda_handler(event("hello"), {})
    assert response["statusCode"] == 500
    assert "service unavailable" in response["body"]
