import importlib.util
import os
import sys

os.environ["FIREHOSE_STREAM"] = "test-stream"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "track", "handler.py")
_spec = importlib.util.spec_from_file_location("analytics_track_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["analytics_track_handler"] = _handler
_spec.loader.exec_module(_handler)
