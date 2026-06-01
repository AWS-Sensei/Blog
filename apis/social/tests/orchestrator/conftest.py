import importlib.util
import os
import sys

os.environ["TABLE_NAME"] = "test-table"
os.environ["FROM_EMAIL"] = "from@example.com"
os.environ["TO_EMAIL"] = "to@example.com"
os.environ["APPROVE_URL"] = "https://example.com/approve"
os.environ["RETRY_URL"] = "https://example.com/retry"
os.environ["BEDROCK_MODEL_ID"] = "anthropic.claude-3-haiku-20240307-v1:0"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "orchestrator", "handler.py")
_spec = importlib.util.spec_from_file_location("social_orchestrator_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["social_orchestrator_handler"] = _handler
_spec.loader.exec_module(_handler)
