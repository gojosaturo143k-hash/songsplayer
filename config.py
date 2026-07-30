import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Yahan int() lagaya hai kyunki Render string mein store karta hai
API_ID = int(os.environ.get("API_ID", 0)) 
API_HASH = os.environ.get("API_HASH")
BOT_USERNAME = os.environ.get("BOT_USERNAME")

# Web Game URL
WEB_URL = os.environ.get("WEB_URL", "https://example.com")

# Firebase Configuration
FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON")

# Render Flask Configuration
PORT = int(os.environ.get("PORT", 10000))
