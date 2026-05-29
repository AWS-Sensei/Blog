import importlib.util
import os
import sys

os.environ["TABLE_NAME"] = "test-table"
os.environ["LINKEDIN_SECRET_NAME"] = "test-secret"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "approver", "handler.py")
_spec = importlib.util.spec_from_file_location("social_approver_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["social_approver_handler"] = _handler
_spec.loader.exec_module(_handler)
