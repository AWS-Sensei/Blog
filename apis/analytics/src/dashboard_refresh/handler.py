import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import boto3

ATHENA_DB = "sensei_analytics"
ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
CACHE_BUCKET = os.environ["CACHE_BUCKET"]
HOURLY_PREFIX = "cache/hourly/"
DASHBOARD_KEY = "cache/dashboard.json"
WINDOW_DAYS = 30

_athena = boto3.client("athena")
_s3 = boto3.client("s3")


def _make_queries(hour_start: datetime, hour_end: datetime) -> dict:
    year  = f"{hour_start.year:04d}"
    month = f"{hour_start.month:02d}"
    day   = f"{hour_start.day:02d}"
    ts_start = hour_start.strftime("%Y-%m-%d %H:%M:%S")
    ts_end   = hour_end.strftime("%Y-%m-%d %H:%M:%S")

    # Partition filter limits Athena to one day; timestamp filter limits to one hour.
    where = (
        f"year = '{year}' AND month = '{month}' AND day = '{day}'"
        f" AND from_iso8601_timestamp(\"timestamp\") >= TIMESTAMP '{ts_start}'"
        f" AND from_iso8601_timestamp(\"timestamp\") <  TIMESTAMP '{ts_end}'"
    )
    return {
        "top_articles": f"""
            SELECT page, COUNT(*) AS views
            FROM sensei_analytics.page_views
            WHERE {where}
              AND REGEXP_LIKE(page, '^/posts/[^/]+/?$')
            GROUP BY page
        """,
        "daily_traffic": f"""
            SELECT
              CAST(from_iso8601_timestamp("timestamp") AS DATE) AS day,
              COUNT(*) AS views,
              COUNT(DISTINCT session_id) AS visitors
            FROM sensei_analytics.page_views
            WHERE {where}
            GROUP BY 1
        """,
        "devices": f"""
            SELECT
              CASE
                WHEN screen_width < 768  THEN 'Mobile'
                WHEN screen_width < 1024 THEN 'Tablet'
                ELSE 'Desktop'
              END AS device,
              COUNT(*) AS views
            FROM sensei_analytics.page_views
            WHERE {where}
            GROUP BY 1
        """,
        "referrers": f"""
            SELECT
              CASE WHEN referrer_domain = '' THEN 'Direct'
                   ELSE referrer_domain END AS source,
              COUNT(*) AS visits
            FROM sensei_analytics.page_views
            WHERE {where}
            GROUP BY 1
            LIMIT 20
        """,
    }


def lambda_handler(event, context):
    now       = datetime.now(timezone.utc)
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    hour_end   = hour_start + timedelta(hours=1)

    # 1. Run 4 Athena queries for the current hour only
    queries = _make_queries(hour_start, hour_end)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_run_query, name, sql): name for name, sql in queries.items()}
        hourly_data = {futures[f]: f.result() for f in as_completed(futures)}

    # 2. Write hourly snapshot
    hourly_key = f"{HOURLY_PREFIX}{hour_start.strftime('%Y-%m-%d-%H')}.json"
    _s3.put_object(
        Bucket=CACHE_BUCKET,
        Key=hourly_key,
        Body=json.dumps(hourly_data).encode(),
        ContentType="application/json",
    )

    # 3. List all hourly files; separate current window from expired ones
    cutoff = now - timedelta(days=WINDOW_DAYS)
    valid_keys, stale_keys = [], []
    pager = _s3.get_paginator("list_objects_v2")
    for page in pager.paginate(Bucket=CACHE_BUCKET, Prefix=HOURLY_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            slug = key.split("/")[-1].replace(".json", "")
            try:
                file_dt = datetime.strptime(slug, "%Y-%m-%d-%H").replace(tzinfo=timezone.utc)
                (stale_keys if file_dt < cutoff else valid_keys).append(key)
            except ValueError:
                pass

    # 4. Merge all valid hourly files
    top_articles  = defaultdict(int)
    daily_traffic = defaultdict(lambda: {"views": 0, "visitors": 0})
    devices       = defaultdict(int)
    referrers     = defaultdict(int)

    for key in valid_keys:
        data = json.loads(_s3.get_object(Bucket=CACHE_BUCKET, Key=key)["Body"].read())
        for row in data.get("top_articles",  []):
            top_articles[row[0]] += int(row[1] or 0)
        for row in data.get("daily_traffic", []):
            daily_traffic[row[0]]["views"]    += int(row[1] or 0)
            daily_traffic[row[0]]["visitors"] += int(row[2] or 0)
        for row in data.get("devices",  []):
            devices[row[0]] += int(row[1] or 0)
        for row in data.get("referrers", []):
            referrers[row[0]] += int(row[1] or 0)

    # 5. Write merged dashboard cache
    _s3.put_object(
        Bucket=CACHE_BUCKET,
        Key=DASHBOARD_KEY,
        Body=json.dumps({
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "top_articles":  [[p, str(v)] for p, v in sorted(top_articles.items(),  key=lambda x: -x[1])[:10]],
            "daily_traffic": [[d, str(v["views"]), str(v["visitors"])] for d, v in sorted(daily_traffic.items())],
            "devices":       [[d, str(v)] for d, v in sorted(devices.items(),  key=lambda x: -x[1])],
            "referrers":     [[s, str(v)] for s, v in sorted(referrers.items(), key=lambda x: -x[1])[:10]],
        }).encode(),
        ContentType="application/json",
    )

    # 6. Delete expired hourly files
    for key in stale_keys:
        _s3.delete_object(Bucket=CACHE_BUCKET, Key=key)


def _run_query(name: str, sql: str) -> list:
    resp = _athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DB},
        WorkGroup=ATHENA_WORKGROUP,
    )
    execution_id = resp["QueryExecutionId"]
    while True:
        state = _athena.get_query_execution(
            QueryExecutionId=execution_id
        )["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Athena query '{name}' {state}")
        time.sleep(1)
    rows = []
    skip_header = True
    for page in _athena.get_paginator("get_query_results").paginate(QueryExecutionId=execution_id):
        for row in page["ResultSet"]["Rows"]:
            if skip_header:
                skip_header = False
                continue
            rows.append([col.get("VarCharValue", "") for col in row["Data"]])
    return rows
