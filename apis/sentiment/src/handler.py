import json
import boto3

comprehend = boto3.client("comprehend", region_name="eu-central-1")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://aws-sensei.cloud",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

SUPPORTED_LANGS = {"en", "de", "fr", "it", "es", "pt", "ar", "hi", "ja", "ko", "zh", "zh-TW"}


def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
        text = body.get("text", "").strip()
        lang = body.get("lang", "en")

        if lang not in SUPPORTED_LANGS:
            lang = "en"

        if not text:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "text is required"}),
            }

        if len(text) > 5000:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "text must be 5000 characters or fewer"}),
            }

        result = comprehend.detect_sentiment(Text=text, LanguageCode=lang)

        sentiment = result["Sentiment"].lower()
        scores = result["SentimentScore"]

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(
                {
                    "sentiment": sentiment,
                    "scores": {
                        "positive": round(scores["Positive"], 4),
                        "negative": round(scores["Negative"], 4),
                        "neutral": round(scores["Neutral"], 4),
                        "mixed": round(scores["Mixed"], 4),
                    },
                }
            ),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
