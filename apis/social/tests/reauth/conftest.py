import importlib.util
import os
import sys

os.environ["LINKEDIN_SECRET_NAME"] = "test-secret"
os.environ["REDIRECT_URI"] = "https://social.aws-sensei.cloud/linkedin/callback"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "reauth", "handler.py")
_spec = importlib.util.spec_from_file_location("social_reauth_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["social_reauth_handler"] = _handler
_spec.loader.exec_module(_handler)
