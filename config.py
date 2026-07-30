import os
import json

# Telegram Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
WEB_URL = os.environ.get("WEB_URL", "https://example.com")

# Render Configuration
PORT = int(os.environ.get("PORT", 5000))

# Firebase Configuration
FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON", "{}")

# Link Code Configuration
LINK_CODE_EXPIRATION_MINUTES = 10
