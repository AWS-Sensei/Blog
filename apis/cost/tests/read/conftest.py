import importlib.util
import os
import sys

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "read", "handler.py")
_spec = importlib.util.spec_from_file_location("cost_read_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["cost_read_handler"] = _handler
_spec.loader.exec_module(_handler)
