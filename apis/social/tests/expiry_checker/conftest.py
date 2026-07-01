import importlib.util
import os
import sys

os.environ["LINKEDIN_SECRET_NAME"] = "test-secret"
os.environ["FROM_EMAIL"] = "noreply@aws-sensei.cloud"
os.environ["TO_EMAIL"] = "marcel.baltzer@hotmail.de"
os.environ["REAUTH_URL"] = "https://social.aws-sensei.cloud/linkedin/reauth"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "expiry_checker", "handler.py")
_spec = importlib.util.spec_from_file_location("social_expiry_checker_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["social_expiry_checker_handler"] = _handler
_spec.loader.exec_module(_handler)
