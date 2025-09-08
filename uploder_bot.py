import discord
from discord.ext import commands
from flask import Flask, request, jsonify
import os
import threading
import asyncio

TOKEN = os.getenv("UPLODER_BOT_TOKEN") 
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)

# --- Flask Webhook ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    channel_id = int(data["channel_id"])
    file_id = int(data["file_id"])

    # Run async fetch in bot loop
    future = asyncio.run_coroutine_threadsafe(fetch_cdn_url(channel_id, file_id), bot.loop)
    cdn_url = future.result()  # Wait for the result

    return jsonify({"cdn_url": cdn_url})

async def fetch_cdn_url(channel_id, file_id):
    channel = bot.get_channel(channel_id)
    if not channel:
        return None
    try:
        message = await channel.fetch_message(file_id)
        if message.attachments:
            return message.attachments[0].url  # temporary Discord CDN link
        else:
            return None
    except Exception as e:
        print(f"Error fetching message: {e}")
        return None

# --- Run Flask in a separate thread ---
def run_flask():
    app.run(host="0.0.0.0", port=5000)

threading.Thread(target=run_flask).start()

# --- Run Discord Bot ---
bot.run(TOKEN)
