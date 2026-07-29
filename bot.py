import asyncio
import json
import random
import threading
import time
from datetime import datetime, timedelta, timezone

import pyrogram
from firebase_admin import credentials, firestore, initialize_app
from flask import Flask, jsonify
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config

# ==========================================
# FIREBASE INITIALIZATION
# ==========================================
try:
    raw_json = config.FIREBASE_CREDENTIALS_JSON.strip()
    if (raw_json.startswith('"') and raw_json.endswith('"')) or (raw_json.startswith("'") and raw_json.endswith("'")):
        raw_json = raw_json[1:-1]
        
    cred_dict = json.loads(raw_json)
    cred = credentials.Certificate(cred_dict)
    firebase_app = initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Firebase initialization failed: {e}")
    db = None

# ==========================================
# FLASK APP (For Render Health Check)
# ==========================================
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Royal Horse Race Bot Running"

@flask_app.route("/health")
def health():
    return "OK", 200

# ==========================================
# PYROGRAM BOT CLIENT
# ==========================================
app = Client(
    "royal_horse_race_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_or_create_user(telegram_id: int, username: str):
    """Ensures user exists in Firestore, returns user doc reference."""
    if not db:
        return None, None
    user_ref = db.collection("users").document(str(telegram_id))
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        user_ref.set({
            "telegram_id": telegram_id,
            "username": username or "Unknown",
            "balance": 1000,  # Starting bonus
            "loan": 0,
            "wins": 0,
            "losses": 0,
            "biggest_win": 0,
            "current_streak": 0,
            "highest_streak": 0,
            "total_bets": 0,
            "royal_rank": "Bronze",
            "created_at": firestore.SERVER_TIMESTAMP
        })
    elif username and user_doc.to_dict().get("username") != username:
        user_ref.update({"username": username})
        
    return user_ref, user_ref.get().to_dict()

def safe_send_message(client, text, chat_id, reply_markup=None, retries=3):
    """Handles Telegram API FloodWait limits automatically."""
    for attempt in range(retries):
        try:
            return client.send_message(chat_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
        except FloodWait as e:
            print(f"FloodWait detected. Sleeping for {e.value} seconds...")
            time.sleep(e.value + 1)
        except Exception as e:
            print(f"Failed to send message: {e}")
            break
    return None

# ==========================================
# COMMAND HANDLERS
# ==========================================

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user = message.from_user
    get_or_create_user(user.id, user.username)
    
    text = (
        f"👑 <b>Welcome to Royal Horse Race, {user.first_name}!</b>\n\n"
        f"Step into the world of virtual equestrian racing. "
        f"Breed, train, and race your majestic horses against players worldwide.\n\n"
        f"🏅 All coins are strictly for entertainment. No real money involved!\n\n"
        f"Choose an option below to begin your journey:"
    )
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Play Royal Horse Race", url=config.WEB_URL)],
        [InlineKeyboardButton("👤 My Profile", callback_data="show_profile"),
         InlineKeyboardButton("❓ Help", callback_data="show_help")]
    ])
    safe_send_message(client, text, message.chat.id, reply_markup=markup)


@app.on_message(filters.command("horsebet") & filters.private)
async def horsebet_command(client, message):
    text = (
        "🏇 <b>Royal Horse Race</b>\n\n"
        "Your next race is waiting!\n"
        "Prepare your steed and place your bets to claim victory.\n\n"
        "Click the button below to open the game."
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Play Now", url=config.WEB_URL)]
    ])
    safe_send_message(client, text, message.chat.id, reply_markup=markup)


@app.on_message(filters.command("link") & filters.private)
async def link_command(client, message):
    if not db:
        return safe_send_message(client, "Database error. Please try again later.", message.chat.id)
        
    code = f"RHR-{random.randint(100000, 999999)}"
    now = datetime.now(timezone.utc)
    
    db.collection("telegram_links").document(code).set({
        "code": code,
        "telegram_id": message.from_user.id,
        "telegram_username": message.from_user.username or "Unknown",
        "created_at": now,
        "expires_at": now + timedelta(minutes=10),
        "used": False
    })
    
    text = (
        f"🔗 <b>Account Linking</b>\n\n"
        f"Your verification code:\n"
        f"<code>{code}</code>\n\n"
        f"⏳ This code expires in 10 minutes and can only be used once.\n\n"
        f"Paste this inside the website to link your account."
    )
    safe_send_message(client, text, message.chat.id)


@app.on_message(filters.command("profile") & filters.private)
async def profile_command(client, message):
    if not db:
        return safe_send_message(client, "Database error.", message.chat.id)
        
    user_ref, user_data = get_or_create_user(message.from_user.id, message.from_user.username)
    if not user_data:
        return safe_send_message(client, "Could not fetch profile.", message.chat.id)

    total = user_data.get("wins", 0) + user_data.get("losses", 0)
    win_rate = (user_data.get("wins", 0) / total * 100) if total > 0 else 0.0

    text = (
        "👑 <b>Your Royal Profile</b>\n\n"
        f"👤 <b>Username:</b> {user_data.get('username', 'N/A')}\n"
        f"🏅 <b>Royal Rank:</b> {user_data.get('royal_rank', 'N/A')}\n"
        f"💰 <b>Balance:</b> {user_data.get('balance', 0):,} coins\n"
        f"🏦 <b>Loan:</b> {user_data.get('loan', 0):,} coins\n\n"
        f"📊 <b>Statistics:</b>\n"
        f"✅ Wins: {user_data.get('wins', 0)}\n"
        f"❌ Losses: {user_data.get('losses', 0)}\n"
        f"📈 Win Rate: {win_rate:.1f}%\n"
        f"🎯 Total Bets: {user_data.get('total_bets', 0)}\n\n"
        f"🔥 <b>Streaks:</b>\n"
        f"⚡ Current: {user_data.get('current_streak', 0)}\n"
        f"🌟 Highest: {user_data.get('highest_streak', 0)}\n\n"
        f"🏆 <b>Biggest Win:</b> {user_data.get('biggest_win', 0):,} coins"
    )
    safe_send_message(client, text, message.chat.id)


@app.on_message(filters.command("give") & filters.private)
async def give_command(client, message):
    if not db:
        return safe_send_message(client, "Database error.", message.chat.id)
        
    try:
        parts = message.text.split()
        if len(parts) != 3:
            return safe_send_message(client, "Usage: /give <username> <amount>", message.chat.id)

        target_username = parts[1].lstrip("@")
        amount = int(parts[2])

        if amount <= 0:
            return safe_send_message(client, "Amount must be a positive number.", message.chat.id)

        if target_username == (message.from_user.username or ""):
            return safe_send_message(client, "You cannot send coins to yourself.", message.chat.id)

        # Firestore Transaction for safe balance transfer
        @firestore.transactional
        def transfer_coins(transaction, sender_ref, receiver_ref, amount):
            sender_doc = sender_ref.get(transaction=transaction)
            receiver_doc = receiver_ref.get(transaction=transaction)

            if not sender_doc.exists:
                raise ValueError("Sender account not found.")
            if not receiver_doc.exists:
                raise ValueError("Receiver account not found.")

            sender_data = sender_doc.to_dict()
            if sender_data.get("balance", 0) < amount:
                raise ValueError("Insufficient balance.")

            # Update balances
            transaction.update(sender_ref, {"balance": sender_data["balance"] - amount})
            receiver_data = receiver_doc.to_dict()
            transaction.update(receiver_ref, {"balance": receiver_data["balance"] + amount})

            # Log transaction
            db.collection("transactions").add({
                "sender_id": str(message.from_user.id),
                "receiver_username": target_username,
                "amount": amount,
                "type": "transfer",
                "created_at": firestore.SERVER_TIMESTAMP
            })

        sender_ref = db.collection("users").document(str(message.from_user.id))
        
        users_ref = db.collection("users").where("username", "==", target_username).limit(1).get()
        if not users_ref:
            return safe_send_message(client, f"❌ User @{target_username} does not play Royal Horse Race.", message.chat.id)
            
        receiver_ref = users_ref[0].reference

        transaction = db.transaction()
        transaction(transfer_coins, sender_ref, receiver_ref, amount)

        safe_send_message(client, f"✅ <b>Transfer Successful!</b>\n\nYou sent <b>{amount:,}</b> coins to @{target_username}.", message.chat.id)

    except ValueError as e:
        safe_send_message(client, f"❌ {str(e)}", message.chat.id)
    except Exception as e:
        print(f"Transfer error: {e}")
        safe_send_message(client, "❌ An error occurred during the transfer.", message.chat.id)


@app.on_message(filters.command("leaderboard") & filters.private)
async def leaderboard_command(client, message):
    if not db:
        return safe_send_message(client, "Database error.", message.chat.id)

    try:
        users_stream = db.collection("users").order_by("wins", direction=firestore.DESCENDING).order_by("balance", direction=firestore.DESCENDING).limit(10).stream()
        
        text = "🏆 <b>Royal Horse Race Leaderboard</b> 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]
        
        for i, user_doc in enumerate(users_stream):
            data = user_doc.to_dict()
            medal = medals[i] if i < 3 else f"<b>{i+1}.</b>"
            text += f"{medal} <b>{data.get('username', 'Unknown')}</b>\n"
            text += f"   👑 {data.get('royal_rank', 'Bronze')} | ✅ {data.get('wins', 0)} Wins | 💰 {data.get('balance', 0):,} coins\n\n"

        safe_send_message(client, text, message.chat.id)
    except Exception as e:
        print(f"Leaderboard error: {e}")
        safe_send_message(client, "Failed to load leaderboard.", message.chat.id)


@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    text = (
        "📖 <b>Royal Horse Race - Help Center</b>\n\n"
        "Here are the commands you can use:\n\n"
        "/start - Open the main menu\n"
        "/horsebet - Quick link to place a bet\n"
        "/profile - View your statistics & balance\n"
        "/link - Generate a code to link your web account\n"
        "/give - Transfer coins to another player\n"
        "/leaderboard - View the top 10 players\n"
        "/help - Show this help message\n\n"
        "⚠️ <b>Note:</b> This is a virtual entertainment game. All coins are fictional. No real money or gambling involved."
    )
    safe_send_message(client, text, message.chat.id)


# ==========================================
# CALLBACK QUERY HANDLERS
# ==========================================
@app.on_callback_query()
async def callback_handler(client, callback_query):
    if callback_query.data == "show_profile":
        await profile_command(client, callback_query.message)
        await callback_query.answer()
    elif callback_query.data == "show_help":
        await help_command(client, callback_query.message)
        await callback_query.answer()


# ==========================================
# PYROGRAM BACKGROUND RUNNER
# ==========================================
def run_pyrogram():
    """Function to safely start Pyrogram in a background thread with its own event loop."""
    # Create a new event loop for this specific thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print("Starting Pyrogram client in background...")
    try:
        loop.run_until_complete(app.start())
        loop.run_forever()
    except Exception as e:
        print(f"Pyrogram stopped: {e}")

# ==========================================
# FLASK STARTUP HOOK (Triggers Bot)
# ==========================================
@flask_app.before_request
def initialize():
    """This runs exactly once when the first request (like Render's /health check) hits the server."""
    if not flask_app._got_first_request:
        # Start Pyrogram in a separate daemon thread
        bot_thread = threading.Thread(target=run_pyrogram, daemon=True)
        bot_thread.start()
        print("Pyrogram background thread spawned.")

# ==========================================
# MAIN EXECUTION BLOCK (For local testing only)
# ==========================================
if __name__ == "__main__":
    print("Starting Royal Horse Race Bot Locally...")
    
    # Start Pyrogram thread first
    bot_thread = threading.Thread(target=run_pyrogram, daemon=True)
    bot_thread.start()
    
    # Then start Flask
    flask_app.run(host="0.0.0.0", port=config.PORT, use_reloader=False)
