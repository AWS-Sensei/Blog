import json
import sys
from unittest.mock import patch

handler = sys.modules["analytics_backfill_handler"]

# Simulated Athena row format: [day, hour, ...fields]
SAMPLE_RESULTS = {
    "top_articles":  [["2026-05-29", "10", "/posts/article-1", "5"]],
    "daily_traffic": [["2026-05-29", "10", "100", "50"]],
    "devices":       [["2026-05-29", "10", "Desktop", "60"]],
    "referrers":     [["2026-05-29", "10", "linkedin.com", "30"]],
}


def mock_run_query(name, sql):
    return SAMPLE_RESULTS.get(name, [])


def test_buckets_results_by_hour_key_and_writes_to_s3():
    with patch.object(handler, "_run_query", side_effect=mock_run_query), \
         patch.object(handler, "_s3") as mock_s3:
        handler.lambda_handler({}, {})

    written_keys = [c[1]["Key"] for c in mock_s3.put_object.call_args_list]
    assert "cache/hourly/2026-05-29-10.json" in written_keys

    body = json.loads(mock_s3.put_object.call_args_list[0][1]["Body"])
    assert body["top_articles"] == [["/posts/article-1", "5"]]
    assert body["devices"] == [["Desktop", "60"]]


def test_returns_written_count():
    with patch.object(handler, "_run_query", side_effect=mock_run_query), \
         patch.object(handler, "_s3"):
        result = handler.lambda_handler({}, {})
    assert result["written"] == 1
