import os
import random
import string
import threading
import asyncio

from flask import Flask
from dotenv import load_dotenv

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import firebase_admin
from firebase_admin import credentials, firestore


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_URL = os.getenv("WEB_URL")


# =====================
# Firebase
# =====================

cred = credentials.Certificate("firebase.json")
firebase_admin.initialize_app(cred)

db = firestore.client()



# =====================
# Flask Server
# =====================

app = Flask(__name__)


@app.route("/")
def home():
    return "Song Room Bot Running"



# =====================
# Telegram Bot
# =====================

bot = Client(
    "song_room_bot",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=BOT_TOKEN
)



def generate_room():

    return ''.join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=6
        )
    )



# =====================
# Commands
# =====================

@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):

    await message.reply_text(
        f"""
🎵 Welcome to Song Room Bot

Hello {message.from_user.first_name} 👋

Create realtime music rooms with friends.

Features:
• 🎧 Group listening rooms
• 👑 Host controls
• ⚡ Real-time sync

Use:
/roomsng

Enjoy 🎶
"""
    )



@bot.on_message(filters.command("roomsng") & filters.group)
async def room_create(client, message):

    rid = generate_room()


    db.collection("rooms").document(rid).set({

        "roomId": rid,
        "hostId": message.from_user.id,
        "hostName": message.from_user.first_name,
        "chatId": message.chat.id,
        "active": True,
        "members": [
            message.from_user.id
        ],
        "song": None,
        "status": "paused"

    })


    join_url = f"{WEB_URL}?room={rid}"


    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎧 Join Room",
                    url=join_url
                )
            ]
        ]
    )


    await message.reply_text(
        f"""
🎵 **Music Room Created**

👑 Host:
{message.from_user.first_name}

🆔 Room ID:
`{rid}`

Invite your friends 🎶
""",
        reply_markup=keyboard
    )



# =====================
# Pyrogram Thread
# =====================

def run_bot():

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


    async def runner():

        await bot.start()

        print("✅ Telegram Bot Started")


        while True:
            await asyncio.sleep(1000)


    loop.run_until_complete(runner())



threading.Thread(
    target=run_bot,
    daemon=True
).start()



# =====================
# Start Flask
# =====================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
