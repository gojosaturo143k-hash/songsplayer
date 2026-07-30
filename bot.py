import os
import random
import logging
from datetime import datetime, timezone, timedelta

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from flask import Flask, jsonify
import firebase_admin
from firebase_admin import credentials, firestore

import config

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Firebase Initialization ---
try:
    cred_dict = json.loads(config.FIREBASE_CREDENTIALS_JSON)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase initialized successfully.")
except Exception as e:
    logger.error(f"Firebase initialization failed: {e}")
    raise

# --- Flask App Setup ---
app = Flask(__name__)

@app.route("/")
def index():
    return "Royal Horse Race Bot Running"

@app.route("/health")
def health():
    return "OK"

# --- Pyrogram Client Setup ---
bot = Client(
    "royal_horse_race_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# --- Helper Functions ---

async def safe_send_message(client, chat_id, text, reply_markup=None):
    """Safely sends a message handling FloodWait exceptions."""
    try:
        await client.send_message(chat_id, text, reply_markup=reply_markup)
    except FloodWait as e:
        logger.warning(f"FloodWait encountered: sleeping for {e.value} seconds.")
        await asyncio.sleep(e.value + 1)
        await client.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")


def get_user(telegram_id):
    """Fetches a linked user document from Firestore using telegram_id."""
    users_ref = db.collection("users")
    query = users_ref.where(filter=firestore.FieldFilter("telegram_id", "==", str(telegram_id))).limit(1)
    docs = query.stream()
    doc = next(docs, None)
    return doc.to_dict() if doc else None


def generate_link_code():
    """Generates a unique 6-digit code for account linking."""
    return f"RHR-{random.randint(100000, 999999)}"


def find_user_by_username(username):
    """Finds a user document in Firestore by their exact username."""
    if not username:
        return None
    users_ref = db.collection("users")
    query = users_ref.where(filter=firestore.FieldFilter("username", "==", username.lower())).limit(1)
    docs = query.stream()
    doc = next(docs, None)
    return doc.reference if doc else None

# --- Command Handlers ---

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    """Handles the /start command with inline buttons."""
    keyboard = [
        [
            {"text": "🎮 Play Royal Horse Race", "url": config.WEB_URL}
        ],
        [
            {"text": "👤 Profile", "callback_data": "profile"},
            {"text": "🔗 Link Account", "callback_data": "link"}
        ]
    ]
    reply_markup = {"inline_keyboard": keyboard}
    text = (
        "Welcome to **Royal Horse Race**! 🏇\n\n"
        "Bet on majestic horses, climb the ranks, and win big."
    )
    await safe_send_message(client, message.chat.id, text, reply_markup=reply_markup)


@bot.on_message(filters.command("horsebet") & filters.private)
async def horsebet_command(client, message):
    """Handles the /horsebet command."""
    keyboard = [[{"text": "🎮 Play Now", "url": config.WEB_URL}]]
    reply_markup = {"inline_keyboard": keyboard}
    text = "🏇 **Royal Horse Race**\n\nClick below to play."
    await safe_send_message(client, message.chat.id, text, reply_markup=reply_markup)


@bot.on_message(filters.command("link") & filters.private)
async def link_command(client, message):
    """Generates a unique, expiring link code and stores it in Firestore."""
    telegram_id = message.from_user.id
    telegram_username = message.from_user.username or "unknown"
    
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=config.LINK_CODE_EXPIRATION_MINUTES)
    code = generate_link_code()
    
    db.collection("telegram_links").document(code).set({
        "code": code,
        "telegram_id": str(telegram_id),
        "telegram_username": telegram_username,
        "created_at": now,
        "expires_at": expires_at,
        "used": False
    })
    
    text = (
        "Your verification code\n\n"
        f"`{code}`\n\n"
        "Paste this inside the website."
    )
    await safe_send_message(client, message.chat.id, text)


@bot.on_message(filters.command("profile") & filters.private)
async def profile_command(client, message):
    """Displays the user's game profile if their account is linked."""
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    
    if not user:
        await safe_send_message(
            client, message.chat.id, 
            "Your Telegram account is not linked yet."
        )
        return

    wins = user.get("wins", 0)
    losses = user.get("losses", 0)
    total_bets = wins + losses
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0.0

    text = (
        "👤 **Your Profile**\n\n"
        f"**Username:** {user.get('username', 'N/A')}\n"
        f"**Royal Rank:** {user.get('royal_rank', 'N/A')}\n"
        f"**Balance:** ${user.get('balance', 0):,.2f}\n"
        f"**Loan:** ${user.get('loan', 0):,.2f}\n\n"
        f"**Wins:** {wins}\n"
        f"**Losses:** {losses}\n"
        f"**Total Bets:** {total_bets}\n"
        f"**Win Rate:** {win_rate:.1f}%\n"
        f"**Biggest Win:** ${user.get('biggest_win', 0):,.2f}"
    )
    await safe_send_message(client, message.chat.id, text)


@bot.on_message(filters.command("give") & filters.private)
async def give_command(client, message):
    """Transfers funds to another user using a Firestore transaction."""
    telegram_id = str(message.from_user.id)
    
    # Parse arguments: /give username amount
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await safe_send_message(client, message.chat.id, "Usage: /give username amount")
        return

    target_username = parts[1].lower().replace("@", "")
    
    try:
        amount = float(parts[2])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await safe_send_message(client, message.chat.id, "Amount must be a positive number.")
        return

    # Fetch sender and receiver references
    sender_ref = None
    users_ref = db.collection("users")
    sender_query = users_ref.where(filter=firestore.FieldFilter("telegram_id", "==", telegram_id)).limit(1)
    sender_doc = next(sender_query.stream(), None)
    if sender_doc:
        sender_ref = sender_doc.reference

    receiver_ref = find_user_by_username(target_username)

    # Validations
    if not sender_ref:
        await safe_send_message(client, message.chat.id, "Your Telegram account is not linked yet.")
        return
    if not receiver_ref:
        await safe_send_message(client, message.chat.id, "Receiver does not exist.")
        return
    if sender_ref.id == receiver_ref.id:
        await safe_send_message(client, message.chat.id, "You cannot send funds to yourself.")
        return

    # Firestore Transaction
    @firestore.async_transactional
    async def transfer_funds(transaction, s_ref, r_ref, transfer_amount):
        s_snap = await s_ref.get(transaction=transaction)
        r_snap = await r_ref.get(transaction=transaction)
        
        s_data = s_snap.to_dict()
        r_data = r_snap.to_dict()
        
        current_balance = s_data.get("balance", 0)
        if current_balance < transfer_amount:
            return False  # Insufficient balance
        
        transaction.update(s_ref, {"balance": current_balance - transfer_amount})
        transaction.update(r_ref, {"balance": r_data.get("balance", 0) + transfer_amount})
        return True

    try:
        success = await transfer_funds(db.transaction(), sender_ref, receiver_ref, amount)
        if success:
            await safe_send_message(client, message.chat.id, "✅ **Transfer Successful**")
        else:
            await safe_send_message(client, message.chat.id, "❌ **Insufficient Balance**")
    except Exception as e:
        logger.error(f"Transfer failed: {e}")
        await safe_send_message(client, message.chat.id, "An error occurred during the transfer.")


# --- Callback Query Handlers ---

@bot.on_callback_query(filters.regex("^profile$"))
async def profile_callback(client, callback_query):
    """Handles the Profile inline button press."""
    await profile_command(client, callback_query.message)
    await callback_query.answer()


@bot.on_callback_query(filters.regex("^link$"))
async def link_callback(client, callback_query):
    """Handles the Link Account inline button press."""
    await link_command(client, callback_query.message)
    await callback_query.answer()


# --- Application Runner ---

def run_app():
    """Starts Flask in a separate thread and Pyrogram synchronously in the main thread."""
    import asyncio
    import threading
    
    # Set event loop policy for Python 3.12 compatibility
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    else:
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run Flask in a daemon thread so it doesn't block Pyrogram
    def start_flask():
        app.run(host="0.0.0.0", port=config.PORT, use_reloader=False)

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask started on 0.0.0.0:{config.PORT}")

    # Run Pyrogram (blocking)
    logger.info("Starting Pyrogram bot...")
    bot.run()

if __name__ == "__main__":
    run_app()
