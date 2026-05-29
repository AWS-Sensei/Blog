import sys
import os

os.environ["WEBSITE_BUCKET"] = "test-bucket"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
