import sys
import os

os.environ["TO_EMAIL"] = "to@example.com"
os.environ["FROM_EMAIL"] = "from@example.com"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
