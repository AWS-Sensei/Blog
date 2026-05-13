import hashlib
import json
import os
import re
from datetime import datetime, timezone

import boto3

FIREHOSE_STREAM = os.environ["FIREHOSE_STREAM"]
_firehose = boto3.client("firehose")

_UA_BROWSERS = [
    ("Edg/", "Edge"),
    ("Chrome/", "Chrome"),
    ("Firefox/", "Firefox"),
    ("Safari/", "Safari"),
    ("OPR/", "Opera"),
]

_BOT_KEYWORDS = [
    "bot", "crawler", "spider", "slurp", "bingbot", "duckduck",
    "baidu", "yandex", "sogou", "exabot", "facebot", "ia_archiver",
    "semrush", "ahrefsbot", "mj12bot", "dotbot", "rogerbot", "petalbot",
    "bytespider", "applebot", "googlebot",
]


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, ValueError):
        return {"statusCode": 400}

    page = body.get("page", "")
    if not isinstance(page, str) or not page.startswith("/"):
        return {"statusCode": 400}

    ua = event.get("headers", {}).get("user-agent", "")
    if _is_bot(ua):
        return {"statusCode": 204}

    page = re.sub(r"[?#].*", "", page)[:512]
    lang = str(body.get("lang", ""))[:10]
    referrer = str(body.get("referrer", ""))
    screen_width = body.get("screen_width")

    referrer_domain = ""
    m = re.match(r"https?://([^/?#]+)", referrer)
    if m and m.group(1) != "aws-sensei.cloud":
        referrer_domain = m.group(1)[:128]

    sw = int(screen_width) if isinstance(screen_width, (int, float)) and 0 < screen_width < 10000 else 0

    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "event": "page_view",
        "page": page,
        "lang": lang,
        "referrer_domain": referrer_domain,
        "browser": _parse_browser(ua),
        "screen_width": sw,
        "session_id": _daily_session_id(ua, lang, sw),
    }

    _firehose.put_record(
        DeliveryStreamName=FIREHOSE_STREAM,
        Record={"Data": (json.dumps(record) + "\n").encode()},
    )
    return {"statusCode": 204}


def _is_bot(ua: str) -> bool:
    ua_lower = ua.lower()
    return any(kw in ua_lower for kw in _BOT_KEYWORDS)


def _parse_browser(ua: str) -> str:
    for token, name in _UA_BROWSERS:
        if token in ua:
            return name
    return "Other"


def _daily_session_id(ua: str, lang: str, screen_width: int) -> str:
    """Daily-rotating, one-way hash — no IP, no cookies, GDPR-safe."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw = f"{ua}|{lang}|{screen_width}|{today}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
