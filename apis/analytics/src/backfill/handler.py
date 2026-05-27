import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import boto3

ATHENA_DB = "sensei_analytics"
ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
CACHE_BUCKET = os.environ["CACHE_BUCKET"]
HOURLY_PREFIX = "cache/hourly/"
WINDOW_DAYS = 30

_athena = boto3.client("athena")
_s3 = boto3.client("s3")


def lambda_handler(event, context):
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    year_start  = f"{cutoff.year:04d}"
    month_start = f"{cutoff.month:02d}"
    day_start   = f"{cutoff.day:02d}"
    ts_start    = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    where = (
        f"(year > '{year_start}'"
        f" OR (year = '{year_start}' AND month > '{month_start}')"
        f" OR (year = '{year_start}' AND month = '{month_start}' AND day >= '{day_start}'))"
        f" AND from_iso8601_timestamp(\"timestamp\") >= TIMESTAMP '{ts_start}'"
    )

    queries = {
        "top_articles": f"""
            SELECT
              CAST(from_iso8601_timestamp("timestamp") AS DATE) AS day,
              HOUR(from_iso8601_timestamp("timestamp"))         AS hour,
              page,
              COUNT(*) AS views
            FROM sensei_analytics.page_views
            WHERE {where}
              AND REGEXP_LIKE(page, '^/posts/[^/]+/?$')
            GROUP BY 1, 2, 3
        """,
        "daily_traffic": f"""
            SELECT
              CAST(from_iso8601_timestamp("timestamp") AS DATE) AS day,
              HOUR(from_iso8601_timestamp("timestamp"))         AS hour,
              COUNT(*) AS views,
              COUNT(DISTINCT session_id) AS visitors
            FROM sensei_analytics.page_views
            WHERE {where}
            GROUP BY 1, 2
        """,
        "devices": f"""
            SELECT
              CAST(from_iso8601_timestamp("timestamp") AS DATE) AS day,
              HOUR(from_iso8601_timestamp("timestamp"))         AS hour,
              CASE
                WHEN screen_width < 768  THEN 'Mobile'
                WHEN screen_width < 1024 THEN 'Tablet'
                ELSE 'Desktop'
              END AS device,
              COUNT(*) AS views
            FROM sensei_analytics.page_views
            WHERE {where}
            GROUP BY 1, 2, 3
        """,
        "referrers": f"""
            SELECT
              CAST(from_iso8601_timestamp("timestamp") AS DATE) AS day,
              HOUR(from_iso8601_timestamp("timestamp"))         AS hour,
              CASE WHEN referrer_domain = '' THEN 'Direct'
                   ELSE referrer_domain END AS source,
              COUNT(*) AS visits
            FROM sensei_analytics.page_views
            WHERE {where}
            GROUP BY 1, 2, 3
        """,
    }

    results = {}
    for name, sql in queries.items():
        print(f"Running backfill query: {name}")
        results[name] = _run_query(name, sql)

    # Bucket results by "YYYY-MM-DD-HH"
    hourly: dict[str, dict] = defaultdict(lambda: {
        "top_articles": [],
        "daily_traffic": [],
        "devices": [],
        "referrers": [],
    })

    for row in results["top_articles"]:
        # day, hour, page, views
        key = f"{row[0]}-{int(row[1]):02d}"
        hourly[key]["top_articles"].append([row[2], row[3]])

    for row in results["daily_traffic"]:
        # day, hour, views, visitors
        key = f"{row[0]}-{int(row[1]):02d}"
        hourly[key]["daily_traffic"].append([row[0], row[2], row[3]])

    for row in results["devices"]:
        # day, hour, device, views
        key = f"{row[0]}-{int(row[1]):02d}"
        hourly[key]["devices"].append([row[2], row[3]])

    for row in results["referrers"]:
        # day, hour, source, visits
        key = f"{row[0]}-{int(row[1]):02d}"
        hourly[key]["referrers"].append([row[2], row[3]])

    written = 0
    for hour_key, data in hourly.items():
        s3_key = f"{HOURLY_PREFIX}{hour_key}.json"
        _s3.put_object(
            Bucket=CACHE_BUCKET,
            Key=s3_key,
            Body=json.dumps(data).encode(),
            ContentType="application/json",
        )
        written += 1

    print(f"Backfill complete: wrote {written} hourly cache files.")
    return {"written": written}


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
            raise RuntimeError(f"Athena backfill query '{name}' {state}")
        time.sleep(2)
    rows = []
    skip_header = True
    for page in _athena.get_paginator("get_query_results").paginate(QueryExecutionId=execution_id):
        for row in page["ResultSet"]["Rows"]:
            if skip_header:
                skip_header = False
                continue
            rows.append([col.get("VarCharValue", "") for col in row["Data"]])
    return rows
