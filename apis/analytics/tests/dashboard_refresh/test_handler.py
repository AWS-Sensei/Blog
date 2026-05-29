import json
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

handler = sys.modules["analytics_dashboard_refresh_handler"]

# Always within the 30-day window regardless of when tests run
_RECENT_HOUR_KEY = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%d-%H")

SAMPLE_STATE = {
    _RECENT_HOUR_KEY: {
        "top_articles": [["/posts/article-1", "10"], ["/posts/article-2", "5"]],
        "daily_traffic": [["2026-05-29", "100", "50"]],
        "devices": [["Desktop", "60"], ["Mobile", "40"]],
        "referrers": [["Direct", "70"], ["linkedin.com", "30"]],
    }
}


def test_aggregates_hourly_state_into_dashboard():
    with patch.object(handler, "_load_state", return_value=SAMPLE_STATE), \
         patch.object(handler, "_run_query", return_value=[]), \
         patch.object(handler, "_s3") as mock_s3:
        handler.lambda_handler({}, {})

    put_calls = {c[1]["Key"]: json.loads(c[1]["Body"]) for c in mock_s3.put_object.call_args_list}
    dashboard = put_calls[handler.DASHBOARD_KEY]

    assert dashboard["top_articles"][0] == ["/posts/article-1", "10"]
    assert dashboard["top_articles"][1] == ["/posts/article-2", "5"]
    assert ["Direct", "70"] in dashboard["referrers"]


def test_prunes_entries_older_than_30_days():
    old_state = {
        "2020-01-01-00": {"top_articles": [], "daily_traffic": [], "devices": [], "referrers": []},
        _RECENT_HOUR_KEY: {"top_articles": [], "daily_traffic": [], "devices": [], "referrers": []},
    }
    with patch.object(handler, "_load_state", return_value=old_state), \
         patch.object(handler, "_run_query", return_value=[]), \
         patch.object(handler, "_s3") as mock_s3:
        handler.lambda_handler({}, {})

    put_calls = {c[1]["Key"]: json.loads(c[1]["Body"]) for c in mock_s3.put_object.call_args_list}
    saved_state = put_calls[handler.MERGED_STATE_KEY]
    assert "2020-01-01-00" not in saved_state
    assert _RECENT_HOUR_KEY in saved_state


def test_writes_both_merged_state_and_dashboard_to_s3():
    with patch.object(handler, "_load_state", return_value={}), \
         patch.object(handler, "_run_query", return_value=[]), \
         patch.object(handler, "_s3") as mock_s3:
        handler.lambda_handler({}, {})

    written_keys = {c[1]["Key"] for c in mock_s3.put_object.call_args_list}
    assert handler.MERGED_STATE_KEY in written_keys
    assert handler.DASHBOARD_KEY in written_keys
