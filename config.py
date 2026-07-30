import os

# ============================
# Telegram Bot
# ============================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")

# ============================
# Website
# ============================
WEB_URL = os.environ.get("WEB_URL", "https://example.com")

# ============================
# Firebase
# ============================
# Render Environment Variable me poora Service Account JSON
# ek hi line me paste karna.
FIREBASE_CREDENTIALS_JSON = os.environ.get(
    "FIREBASE_CREDENTIALS_JSON", ""
)

# ============================
# Flask / Render
# ============================
PORT = int(os.environ.get("PORT", 10000))
