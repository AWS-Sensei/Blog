---
title: "How I Replaced Google Analytics with 3 AWS Services"
date: 2026-05-18T00:00:00+02:00
lastmod: 2026-05-18T00:00:00+02:00
draft: false
author: "Marcel"
description: "Privacy-first analytics with CloudFront, Kinesis Firehose, and Athena — no tracking cookies, no third parties, full control over your data."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "CloudFront", "Kinesis", "Athena", "Lambda", "Analytics", "Privacy", "SAM", "Serverless"]
lightgallery: true
---

{{< listen >}}

Google Analytics is the obvious choice for blog analytics — free, ready to go, works out of the box. But it also means: third-party cookies, data sharing with Google, and a consent banner you have to make GDPR-compliant somehow. For a blog about AWS, it seemed natural to solve this differently.

The result: a custom analytics system built from three AWS services that sets no cookies, stores no IP addresses, and respects DNT — with a live dashboard at [/stats](/stats/).

## The Architecture

```text
Browser
  │  POST /track  (keepalive fetch)
  ▼
CloudFront Function  ──  strip cookies
  │
  ▼
API Gateway → Lambda  ──  bot filter, session hash, Firehose
  │
  ▼
Kinesis Firehose  ──  GZIP, Hive prefix
  │
  ▼
S3  ──  events/year=.../month=.../day=.../
  │
  ▼
Athena + Glue  ──  SQL over raw data
  │
  ▼
Lambda (hourly)  ──  4 parallel queries → S3 cache
  │
  ▼
GET /dashboard  →  ECharts frontend
```

Each layer has exactly one responsibility. No monolithic service, no database to maintain.

## Privacy by Design

This was the first and most important decision. The rules:

- **No IP address** is stored
- **No cookies**, no persistent IDs
- **DNT is respected** — users with Do Not Track enabled are not tracked
- **Session ID** is a daily-rotating SHA256 hash: `SHA256(date + User-Agent + screen width)` — resets daily, not reversible, but still enables a unique visitor approximation

The tracking script embedded in the blog is intentionally minimal:

```javascript
if (navigator.doNotTrack === '1') return;

fetch('/track', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    page: location.pathname,
    lang: document.documentElement.lang,
    referrer: document.referrer ? new URL(document.referrer).hostname : '',
    screen_width: screen.width
  }),
  keepalive: true
}).catch(() => {});
```

`keepalive: true` ensures the request fires even if the user navigates away immediately after a page load. The `.catch(() => {})` silently swallows errors if analytics is temporarily unavailable.

## CloudFront Function: Stripping Cookies

CloudFront forwards `/track` requests to API Gateway. To ensure no browser cookies reach the backend, a CloudFront Function sits in front:

```javascript
function handler(event) {
  var request = event.request;
  request.cookies = {};
  return request;
}
```

Three lines. The function runs at the edge before the request ever reaches the origin.

## Lambda: Bot Filter and Session Hash

The Lambda function does three things: filter bots, compute the session ID, write the event to Firehose.

**Bot filtering** by User-Agent:

```python
BOT_PATTERNS = re.compile(
    r'bot|crawl|spider|slurp|facebookexternalhit|'
    r'python-requests|curl|wget|go-http-client',
    re.IGNORECASE
)

if BOT_PATTERNS.search(ua):
    return {"statusCode": 200, "body": "ok"}
```

Bots get a silent 200 — no error, no retry storm.

**Session ID** without persistent data:

```python
date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
raw = f"{date_str}|{user_agent}|{screen_width}"
session_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
```

The hash rotates automatically every day. Two visits from the same user on the same day count as one session; the next day it's a new one.

The event is then written as compact JSON to Kinesis Firehose:

```python
record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "event": "pageview",
    "page": body.get("page", ""),
    "lang": body.get("lang", ""),
    "referrer_domain": body.get("referrer", ""),
    "browser": browser,
    "screen_width": screen_width,
    "session_id": session_id,
}
firehose.put_record(
    DeliveryStreamName=STREAM_NAME,
    Record={"Data": (json.dumps(record) + "\n").encode()}
)
```

## Kinesis Firehose: Data into S3

Firehose buffers events (60 seconds or 5 MB, whichever comes first), compresses with GZIP, and writes to S3 with a Hive-compatible prefix:

```text
events/year=2026/month=05/day=18/analytics-1-2026-05-18-...gz
```

This format lets Athena read only the relevant partitions rather than scanning all data.

## Glue Table with Partition Projection

Instead of a Glue Crawler that needs to run regularly, I use **Partition Projection**. The partition structure is declared directly in the Glue schema:

```yaml
Parameters:
  projection.enabled: "true"
  projection.year.type: "integer"
  projection.year.range: "2026,2030"
  projection.month.type: "integer"
  projection.month.range: "1,12"
  projection.month.digits: "2"
  projection.day.type: "integer"
  projection.day.range: "1,31"
  projection.day.digits: "2"
  storage.location.template: "s3://BUCKET/events/year=${year}/month=${month}/day=${day}/"
```

No crawler, no daily costs for metadata updates. Athena computes the partition paths itself.

## The Dashboard

An EventBridge schedule triggers a Lambda every hour that runs four Athena queries in parallel:

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(_run_query, name, sql): name
        for name, sql in _QUERIES.items()
    }
```

The queries:

| Query | What |
|-------|------|
| `daily_traffic` | Views + unique visitors per day, last 30 days |
| `top_articles` | Top 10 posts by views, last 30 days |
| `referrers` | Top 10 traffic sources, last 30 days |
| `devices` | Mobile / Tablet / Desktop by screen width |

The result is stored as `cache/dashboard.json` in S3. GET `/dashboard` reads this file — Athena is not queried on every dashboard request.

The frontend at [/stats](/stats/) renders the data with ECharts, is dark mode aware, and loads everything client-side:

```javascript
fetch('/dashboard')
  .then(r => r.json())
  .then(d => render(d));
```

## Custom Domain: analytics.aws-sensei.cloud

One important architectural decision: the analytics API has its own subdomain rather than an SSM parameter dependency on the infrastructure stack.

This solves the chicken-and-egg problem: CloudFront can have `analytics.aws-sensei.cloud` configured as an origin even before the analytics API exists. Requests to `/track` will silently fail (`.catch(() => {})`), but the rest of the site works normally. Once the analytics stack is deployed, everything works — without needing to redeploy the infra stack.

## Costs

For the traffic of a personal blog: **under one dollar per month**.

- **Firehose**: $0.029 per GB — with a few KB of events per day, essentially zero
- **S3**: $0.023 per GB storage + minimal PUT/GET costs
- **Athena**: $5 per TB scanned — with GZIP + Partition Projection, a few cents per month
- **Lambda**: free under the free tier
- **EventBridge**: free for standard schedules (first million events/month)

Google Analytics is free — but the price is data control and privacy. This stack costs cents, and all the data is mine.

## Result

The dashboard is live at [/stats](/stats/). Daily traffic, top articles, referrers, and device breakdown — all from my own data, no third parties, no cookies.

---

{{< chat >}}
