import os
import sys
import asyncio
import logging
import random
import string
import json
from dotenv import load_dotenv

# Import Flask for Render Web Service port binding
from flask import Flask

# Import Aiogram 3.x for Telegram Bot
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# Import Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_URL = os.getenv("WEB_URL")

if not BOT_TOKEN:
    logging.critical("BOT_TOKEN is missing in environment variables.")
    sys.exit(1)

# Setup logging for production debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==========================================
# 2. FIREBASE INITIALIZATION (ENV METHOD)
# ==========================================

try:
    # Read credentials directly from Environment Variable to avoid file corruption issues
    firebase_creds_json = os.getenv("FIREBASE_CREDS")
    
    if not firebase_creds_json:
        logging.critical("FIREBASE_CREDS environment variable is missing in Render!")
        sys.exit(1)
        
    # Parse string to dictionary
    cred_dict = json.loads(firebase_creds_json)
    cred = credentials.Certificate(cred_dict)
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        
    # Initialize Firestore database
    db = firestore.client()
    logger.info("Firebase initialized successfully via Environment Variable.")
    
except Exception as e:
    logger.critical(f"Failed to initialize Firebase: {e}")
    sys.exit(1)

# ==========================================
# 3. FLASK APP SETUP (For Render)
# ==========================================

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    """Health check endpoint required by Render Free Web Service."""
    return "Song Room Bot Running", 200

def run_flask():
    """Synchronous function to run Flask using asyncio's built-in to_thread."""
    # Bind to 0.0.0.0 and the PORT defined by Render (defaults to 10000)
    port = int(os.getenv("PORT", 10000))
    # Use threading=False to prevent Flask from spawning extra threads
    app.run(host='0.0.0.0', port=port, threaded=False)

# ==========================================
# 4. AIogram 3.x BOT SETUP
# ==========================================

# Initialize Router and Dispatcher
router = Router()
dp = Dispatcher()
dp.include_router(router)

# Initialize Bot with default properties
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle the /start command in private chats."""
    first_name = message.from_user.first_name or "Friend"
    
    response_text = (
        "🎵 <b>Welcome to Song Room Bot</b>\n\n"
        f"Hello {first_name} 👋\n\n"
        "Create realtime music rooms with your friends.\n\n"
        "<b>Features:</b>\n"
        "• 🎧 Group listening rooms\n"
        "• 👑 Host controls\n"
        "• ⚡ Real-time sync\n\n"
        "Add me to your group and use:\n"
        "<code>/roomsng</code>\n\n"
        "Enjoy music together 🎶"
    )
    
    await message.answer(response_text)

@router.message(Command("roomsng"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_roomsng(message: Message):
    """Handle the /roomsng command in groups to create a music room."""
    user = message.from_user
    chat_id = message.chat.id
    
    # Generate a random 6-character Room ID (Uppercase letters + Numbers)
    room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # Generate Join URL using the provided WEB_URL (Netlify)
    join_url = f"{WEB_URL}?room={room_id}"
    
    # Define Firestore document data
    room_data = {
        "roomId": room_id,
        "hostId": user.id,
        "hostName": user.first_name or "Unknown Host",
        "chatId": chat_id,
        "active": True,
        "members": [user.id],
        "song": None,
        "status": "paused"
    }
    
    try:
        # Firebase is synchronous, so we MUST run it in a thread 
        # otherwise it blocks Aiogram's async event loop and fails silently.
        def save_to_firebase():
            doc_ref = db.collection("rooms").document(room_id)
            doc_ref.set(room_data)
            
        await asyncio.to_thread(save_to_firebase)
        logger.info(f"Room {room_id} created in chat {chat_id} by user {user.id}")
        
    except Exception as e:
        logger.error(f"Firebase error while creating room: {e}")
        await message.answer("❌ An error occurred while creating the room. Please try again.")
        return
    
    # Build the response text
    response_text = (
        "🎵 <b>Music Room Created</b>\n\n"
        f"👑 <b>Host:</b>\n{room_data['hostName']}\n\n"
        f"🆔 <b>Room ID:</b>\n<code>{room_id}</code>\n\n"
        "Invite your friends and listen together 🎶"
    )
    
    # Create Inline Keyboard
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎧 Join Room", url=join_url)]
    ])
    
    # Send message to group
    await message.answer(response_text, reply_markup=keyboard)

# ==========================================
# 5. MAIN EXECUTION & ASYNCIO MANAGEMENT
# ==========================================

async def main():
    """Main entry point to run Flask and Aiogram together cleanly."""
    logger.info("Starting Bot and Web Server...")
    
    # Delete webhook to ensure clean polling state
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Create the polling task (non-blocking)
    bot_task = asyncio.create_task(dp.start_polling(bot))
    
    try:
        # Run Flask in a separate thread managed by the event loop
        # This avoids manual threading hacks and keeps everything in one loop
        await asyncio.to_thread(run_flask)
    except asyncio.CancelledError:
        logger.info("Flask server shutdown signal received.")
    finally:
        # Cleanup: Stop polling and close bot session if Flask stops
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Bot shutdown complete.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user.")
