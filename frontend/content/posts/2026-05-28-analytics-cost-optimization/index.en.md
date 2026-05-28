---
title: "From 900,000 to 3: Drastically Reducing S3 Costs with Incremental Caching"
date: 2026-05-28T00:00:00+02:00
lastmod: 2026-05-28T00:00:00+02:00
draft: false
author: "Marcel"
socialmedia: true
description: "How a scheduled Lambda was silently generating hundreds of thousands of S3 requests per day — and how three targeted changes solved the problem at the root."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "S3", "Athena", "Lambda", "Analytics", "Cost Optimization", "Serverless", "SAM"]
lightgallery: true
---

{{< listen >}}

$4.64 in two days. For a blog with modest traffic, that's an unexpected surprise in the AWS Cost Explorer. The culprit was easy to find — but the fix took three iterations worth writing down.

## The Problem

My [analytics system](/posts/2026-05-18-privacy-analytics/) is built on Kinesis Firehose → S3 → Athena. A scheduled Lambda runs every hour, queries Athena, and writes the result as JSON to S3 where the dashboard reads it.

The original Lambda looked conceptually like this:

```python
# 4 queries, each scanning 30 days
SELECT page, COUNT(*) FROM page_views
WHERE timestamp >= CURRENT_DATE - INTERVAL '30' DAY
GROUP BY page
```

Four queries. Every hour. Sounds harmless.

## Why Athena Generates So Many S3 Requests

Athena is not a database server with an index — it's a query engine that works directly on S3 files. For each query, Athena internally does:

1. **LIST** — enumerate all files in the relevant partitions
2. **GET** — read and decompress each file individually
3. **PUT** — write results to `athena-results/`

With Hive partitions by `year/month/day` and 30 days of history, that means ~30 partition prefixes per query, each with several GZIP files. Four queries, 24 times a day:

```text
4 queries × ~8,000 S3 requests/query × 24 runs/day ≈ 768,000 Tier-1 requests/day
```

Tier-1 (PUT/LIST) costs $0.005 per 1,000 requests in eu-central-1 — that's nearly $4/day.

## Step 1: Let Athena Scan Only the Current Hour

The core insight: the dashboard needs 30 days of data, but Athena doesn't have to scan 30 days on every run. If hourly snapshots are accumulated, it's enough to ask Athena about the **current hour** only.

```python
# One day as partition filter, one hour as timestamp filter
where = (
    f"year = '{year}' AND month = '{month}' AND day = '{day}'"
    f" AND from_iso8601_timestamp(\"timestamp\") >= TIMESTAMP '{ts_start}'"
    f" AND from_iso8601_timestamp(\"timestamp\") <  TIMESTAMP '{ts_end}'"
)
```

The partition filter limits Athena to one day (instead of 30), the timestamp filter to one hour. The result is saved as `cache/hourly/YYYY-MM-DD-HH.json`. The Lambda then merges all existing hourly files in Python into a dashboard.

**Savings: ~97%** of Athena scan costs.

## Step 2: Optimizing the Merge Step

Look closely and you'll spot the next problem: reading up to 720 hourly files every hour (`30 days × 24h`) means 720 S3 GET requests per run.

The fix: instead of re-reading all files, maintain an accumulated `merged_state.json` — a dict with all hours as keys:

```json
{
  "2026-05-27-14": {
    "top_articles": [["page", "views"], ...],
    "daily_traffic": [...],
    ...
  }
}
```

Each Lambda run then only needs to:

1. GET `merged_state.json`
2. Query Athena for the last hour
3. Insert new hour, remove hours > 30 days old
4. PUT `merged_state.json`
5. PUT `dashboard.json`

**3 S3 requests per run** instead of 720.

## Step 3: Querying the Right Hour

One more subtle bug: the original code queried the **current** hour:

```python
hour_start = now.replace(minute=0, second=0, microsecond=0)  # e.g. 14:00
hour_end   = hour_start + timedelta(hours=1)                  # 15:00
```

If the Lambda fires at 14:05, the snapshot for hour 14 only contains 5 minutes of data. The remaining 55 minutes are never captured.

Fix: always query the **previous completed hour**:

```python
hour_end   = now.replace(minute=0, second=0, microsecond=0)  # 14:00
hour_start = hour_end - timedelta(hours=1)                    # 13:00
```

Run at 14:05 → complete hour 13:00–14:00. No data gaps, one hour of delay in the dashboard.

## The Result

| | Before | After |
| --- | --- | --- |
| Athena scans | 30 days / run | 1 hour / run |
| S3 requests / run | ~8,000 | 3 |
| S3 requests / day | ~768,000 | ~72 |
| Estimated cost / day | up to ~$3 | <$0.01 |

There's also a one-time **backfill Lambda** that prepares the last 30 days as historical hourly snapshots — so the dashboard isn't empty on first run.

## Takeaway

The pattern generalizes: whenever a scheduled query recomputes historical data from scratch, it's worth asking — does it really need to start over every time? Often a small accumulated state object is enough to limit the scan to what's new. Like an incremental backup: only the delta, not everything.

The full code is available on [GitHub](https://github.com/AWS-Sensei/Blog/tree/main/apis/analytics).

---

{{< chat >}}
