import importlib.util
import os
import sys

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "refresh", "handler.py")
_spec = importlib.util.spec_from_file_location("cost_refresh_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["cost_refresh_handler"] = _handler
_spec.loader.exec_module(_handler)
