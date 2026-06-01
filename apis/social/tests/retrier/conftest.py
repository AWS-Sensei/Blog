import importlib.util
import os
import sys

os.environ["TABLE_NAME"] = "test-table"
os.environ["ORCHESTRATOR_FUNCTION_NAME"] = "sensei-social-orchestrator"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "retrier", "handler.py")
_spec = importlib.util.spec_from_file_location("social_retrier_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["social_retrier_handler"] = _handler
_spec.loader.exec_module(_handler)
