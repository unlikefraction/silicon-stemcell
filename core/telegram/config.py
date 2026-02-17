import os
import sys

# Add project root to path so we can import env
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from env import TELEGRAM_BOT_TOKEN

BOT_TOKEN = TELEGRAM_BOT_TOKEN
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
CONTACTS_FILE = os.path.join(os.path.dirname(__file__), "contacts.json")
