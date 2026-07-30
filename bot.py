import asyncio
import json
import random
import threading
import time
import os
from datetime import datetime, timedelta, timezone

from firebase_admin import credentials, firestore, initialize_app
from flask import Flask
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config

# ==========================================
# FIREBASE INITIALIZATION
# ==========================================
db = None
try:
    raw_json = config.FIREBASE_CREDENTIALS_JSON.strip()
    if (raw_json.startswith('"') and raw_json.endswith('"')) or (raw_json.startswith("'") and raw_json.endswith("'")):
        raw_json = raw_json[1:-1]
    cred_dict = json.loads(raw_json)
    cred = credentials.Certificate(cred_dict)
    firebase_app = initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase Connected Successfully!")
except Exception as e:
    print(f"❌ Firebase initialization failed: {e}")

# ==========================================
# FLASK APP (Health Check)
# ==========================================
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Royal Horse Race Bot Running"

@flask_app.route("/health")
def health():
    return "OK", 200

# ==========================================
# PYROGRAM CLIENT
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
    if not db: return None, None
    user_ref = db.collection("users").document(str(telegram_id))
    user_doc = user_ref.get()
    if not user_doc.exists:
        user_ref.set({
            "telegram_id": telegram_id, "username": username or "Unknown", "balance": 1000,
            "loan": 0, "wins": 0, "losses": 0, "biggest_win": 0, "current_streak": 0,
            "highest_streak": 0, "total_bets": 0, "royal_rank": "Bronze", "created_at": firestore.SERVER_TIMESTAMP
        })
    elif username and user_doc.to_dict().get("username") != username:
        user_ref.update({"username": username})
    return user_ref, user_ref.get().to_dict()

def safe_send_message(client, text, chat_id, reply_markup=None, retries=3):
    for attempt in range(retries):
        try:
            return client.send_message(chat_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
        except FloodWait as e:
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
    text = "🏇 <b>Royal Horse Race</b>\n\nYour next race is waiting!\nPrepare your steed and place your bets to claim victory.\n\nClick the button below to open the game."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Now", url=config.WEB_URL)]])
    safe_send_message(client, text, message.chat.id, reply_markup=markup)

@app.on_message(filters.command("link") & filters.private)
async def link_command(client, message):
    if not db: return safe_send_message(client, "Database error.", message.chat.id)
    code = f"RHR-{random.randint(100000, 999999)}"
    now = datetime.now(timezone.utc)
    db.collection("telegram_links").document(code).set({
        "code": code, "telegram_id": message.from_user.id, "telegram_username": message.from_user.username or "Unknown",
        "created_at": now, "expires_at": now + timedelta(minutes=10), "used": False
    })
    text = f"🔗 <b>Account Linking</b>\n\nYour verification code:\n<code>{code}</code>\n\n⏳ This code expires in 10 minutes and can only be used once.\n\nPaste this inside the website to link your account."
    safe_send_message(client, text, message.chat.id)

@app.on_message(filters.command("profile") & filters.private)
async def profile_command(client, message):
    if not db: return safe_send_message(client, "Database error.", message.chat.id)
    user_ref, u = get_or_create_user(message.from_user.id, message.from_user.username)
    if not u: return safe_send_message(client, "Could not fetch profile.", message.chat.id)
    total = u.get("wins", 0) + u.get("losses", 0)
    wr = (u.get("wins", 0) / total * 100) if total > 0 else 0.0
    text = (
        "👑 <b>Your Royal Profile</b>\n\n"
        f"👤 <b>Username:</b> {u.get('username', 'N/A')}\n🏅 <b>Royal Rank:</b> {u.get('royal_rank', 'N/A')}\n"
        f"💰 <b>Balance:</b> {u.get('balance', 0):,} coins\n🏦 <b>Loan:</b> {u.get('loan', 0):,} coins\n\n"
        f"📊 <b>Statistics:</b>\n✅ Wins: {u.get('wins', 0)}\n❌ Losses: {u.get('losses', 0)}\n📈 Win Rate: {wr:.1f}%\n"
        f"🎯 Total Bets: {u.get('total_bets', 0)}\n\n🔥 <b>Streaks:</b>\n⚡ Current: {u.get('current_streak', 0)}\n"
        f"🌟 Highest: {u.get('highest_streak', 0)}\n\n🏆 <b>Biggest Win:</b> {u.get('biggest_win', 0):,} coins"
    )
    safe_send_message(client, text, message.chat.id)

@app.on_message(filters.command("give") & filters.private)
async def give_command(client, message):
    if not db: return safe_send_message(client, "Database error.", message.chat.id)
    try:
        parts = message.text.split()
        if len(parts) != 3: return safe_send_message(client, "Usage: /give <username> <amount>", message.chat.id)
        target_username = parts[1].lstrip("@")
        amount = int(parts[2])
        if amount <= 0: return safe_send_message(client, "Amount must be positive.", message.chat.id)
        if target_username == (message.from_user.username or ""): return safe_send_message(client, "Cannot send to yourself.", message.chat.id)

        @firestore.transactional
        def transfer(transaction, s_ref, r_ref, amt):
            s_doc, r_doc = s_ref.get(transaction=transaction), r_ref.get(transaction=transaction)
            if not s_doc.exists or not r_doc.exists: raise ValueError("User not found.")
            if s_doc.to_dict().get("balance", 0) < amt: raise ValueError("Insufficient balance.")
            transaction.update(s_ref, {"balance": s_doc.to_dict()["balance"] - amt})
            transaction.update(r_ref, {"balance": r_doc.to_dict()["balance"] + amt})
            db.collection("transactions").add({"sender_id": str(message.from_user.id), "receiver_username": target_username, "amount": amt, "type": "transfer", "created_at": firestore.SERVER_TIMESTAMP})

        s_ref = db.collection("users").document(str(message.from_user.id))
        users = db.collection("users").where("username", "==", target_username).limit(1).get()
        if not users: return safe_send_message(client, f"❌ User @{target_username} not found.", message.chat.id)
        db.transaction()(transfer, s_ref, users[0].reference, amount)
        safe_send_message(client, f"✅ <b>Transfer Successful!</b>\n\nSent <b>{amount:,}</b> coins to @{target_username}.", message.chat.id)
    except ValueError as e: safe_send_message(client, f"❌ {str(e)}", message.chat.id)
    except Exception as e: 
        print(f"Transfer error: {e}")
        safe_send_message(client, "❌ Transfer error.", message.chat.id)

@app.on_message(filters.command("leaderboard") & filters.private)
async def leaderboard_command(client, message):
    if not db: return safe_send_message(client, "Database error.", message.chat.id)
    try:
        users_stream = db.collection("users").order_by("wins", direction=firestore.DESCENDING).order_by("balance", direction=firestore.DESCENDING).limit(10).stream()
        text = "🏆 <b>Royal Horse Race Leaderboard</b> 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, doc in enumerate(users_stream):
            d = doc.to_dict()
            m = medals[i] if i < 3 else f"<b>{i+1}.</b>"
            text += f"{m} <b>{d.get('username', 'Unknown')}</b>\n   👑 {d.get('royal_rank', 'Bronze')} | ✅ {d.get('wins', 0)} Wins | 💰 {d.get('balance', 0):,} coins\n\n"
        safe_send_message(client, text, message.chat.id)
    except Exception as e:
        print(f"LB error: {e}")
        safe_send_message(client, "Failed to load leaderboard.", message.chat.id)

@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    text = (
        "📖 <b>Royal Horse Race - Help Center</b>\n\n"
        "/start - Open the main menu\n/horsebet - Quick link to place a bet\n/profile - View your statistics & balance\n"
        "/link - Generate a code to link your web account\n/give - Transfer coins to another player\n"
        "/leaderboard - View the top 10 players\n/help - Show this help message\n\n"
        "⚠️ <b>Note:</b> This is a virtual entertainment game. All coins are fictional. No real money or gambling involved."
    )
    safe_send_message(client, text, message.chat.id)

@app.on_callback_query()
async def callback_handler(client, callback_query):
    if callback_query.data == "show_profile": await profile_command(client, callback_query.message)
    elif callback_query.data == "show_help": await help_command(client, callback_query.message)
    await callback_query.answer()

# ==========================================
# PYROGRAM SAFE RUNNER
# ==========================================
def run_pyrogram_safely():
    print("🚀 Attempting to start Telegram Bot...")
    try:
        if not config.API_ID or not config.API_HASH or not config.BOT_TOKEN:
            print("❌ Missing BOT_TOKEN, API_ID, or API_HASH in environment variables.")
            return
            
        # YEH LINE SABSE ZAROORI HAI: Yeh bot ko forcefully start karega aur agar koi bhi 
        # internal error hoga (API_ID galat, token invalid, etc) toh woh directly yahan print hoga.
        app.run()
        
    except Exception as e:
        print(f"❌ Bot failed to start: {e}")

# ==========================================
# GUNICORN PRELOAD FIX
# ==========================================
# Yeh check isliye hai kyunki Render 'gunicorn --preload' use karta hai.
# Isse bot sirf ek baar start hoga, worker fork hone pe dobara nahi hoga.
_bot_thread_started = False

def start_bot_if_needed():
    global _bot_thread_started
    # Sirf worker process mein start karo (Render pe iska matlab worker PID match karna)
    if not _bot_thread_started and str(os.getpid()) == os.environ.get("WORKER_PID", str(os.getpid())):
        _bot_thread_started = True
        threading.Thread(target=run_pyrogram_safely, daemon=True).start()

# Jab bhi Flask koi request handle kare, yeh check karega ki bot start hua ki nahi.
@flask_app.before_request
def ensure_bot_running():
    start_bot_if_needed()

# Fallback: Agar Flask route hit na ho toh bhi bot start ho jaye (Local testing ke liye)
if __name__ == "__main__":
    start_bot_if_needed()
    flask_app.run(host="0.0.0.0", port=config.PORT, use_reloader=False)
