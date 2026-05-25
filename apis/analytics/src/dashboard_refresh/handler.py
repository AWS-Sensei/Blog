import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import boto3

ATHENA_DB = "sensei_analytics"
ATHENA_WORKGROUP = os.environ["ATHENA_WORKGROUP"]
CACHE_BUCKET = os.environ["CACHE_BUCKET"]
CACHE_KEY = "cache/dashboard.json"

_athena = boto3.client("athena")
_s3 = boto3.client("s3")

_QUERIES = {
    "top_articles": """
        SELECT page, COUNT(*) AS views
        FROM sensei_analytics.page_views
        WHERE page LIKE '/posts/%'
          AND CAST(from_iso8601_timestamp("timestamp") AS DATE)
              >= CURRENT_DATE - INTERVAL '7' DAY
        GROUP BY page
        ORDER BY views DESC
        LIMIT 10
    """,
    "daily_traffic": """
        SELECT
          CAST(from_iso8601_timestamp("timestamp") AS DATE) AS day,
          COUNT(*) AS views,
          COUNT(DISTINCT session_id) AS visitors
        FROM sensei_analytics.page_views
        WHERE CAST(from_iso8601_timestamp("timestamp") AS DATE)
              >= CURRENT_DATE - INTERVAL '30' DAY
        GROUP BY 1
        ORDER BY 1
    """,
    "devices": """
        SELECT
          CASE
            WHEN screen_width < 768  THEN 'Mobile'
            WHEN screen_width < 1024 THEN 'Tablet'
            ELSE 'Desktop'
          END AS device,
          COUNT(*) AS views
        FROM sensei_analytics.page_views
        WHERE CAST(from_iso8601_timestamp("timestamp") AS DATE)
              >= CURRENT_DATE - INTERVAL '30' DAY
        GROUP BY 1
        ORDER BY views DESC
    """,
    "referrers": """
        SELECT
          CASE WHEN referrer_domain = '' THEN 'Direct'
               ELSE referrer_domain END AS source,
          COUNT(*) AS visits
        FROM sensei_analytics.page_views
        WHERE CAST(from_iso8601_timestamp("timestamp") AS DATE)
              >= CURRENT_DATE - INTERVAL '30' DAY
        GROUP BY 1
        ORDER BY visits DESC
        LIMIT 10
    """,
}


def lambda_handler(event, context):
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_run_query, name, sql): name
            for name, sql in _QUERIES.items()
        }
        results = {}
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **results,
    }
    _s3.put_object(
        Bucket=CACHE_BUCKET,
        Key=CACHE_KEY,
        Body=json.dumps(payload).encode(),
        ContentType="application/json",
    )


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
    paginator = _athena.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=execution_id):
        for row in page["ResultSet"]["Rows"]:
            if skip_header:
                skip_header = False
                continue
            rows.append([col.get("VarCharValue", "") for col in row["Data"]])
    return rows
