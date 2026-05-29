import importlib.util
import os
import sys

os.environ["CONNECTIONS_TABLE"] = "test-connections"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "connect", "handler.py")
_spec = importlib.util.spec_from_file_location("chat_connect_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["chat_connect_handler"] = _handler
_spec.loader.exec_module(_handler)
