import importlib.util
import os
import sys

os.environ["ATHENA_WORKGROUP"] = "test-workgroup"
os.environ["CACHE_BUCKET"] = "test-bucket"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "backfill", "handler.py")
_spec = importlib.util.spec_from_file_location("analytics_backfill_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["analytics_backfill_handler"] = _handler
_spec.loader.exec_module(_handler)
