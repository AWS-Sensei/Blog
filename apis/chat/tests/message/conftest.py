import importlib.util
import os
import sys

os.environ["CONNECTIONS_TABLE"] = "test-connections"
os.environ["MESSAGES_TABLE"] = "test-messages"

_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "message", "handler.py")
_spec = importlib.util.spec_from_file_location("chat_message_handler", _path)
_handler = importlib.util.module_from_spec(_spec)
sys.modules["chat_message_handler"] = _handler
_spec.loader.exec_module(_handler)
