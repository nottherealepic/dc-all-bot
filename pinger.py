import os
import aiohttp
import discord
import pytz
import threading
import asyncio
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from flask import Flask, send_from_directory, request, jsonify

# Load env variables
load_dotenv()
TOKEN = os.getenv("PINGER_TOKEN")
CHANNEL_ID = int(os.getenv("PINGER_CHANNEL_ID"))
MESSAGE_ID = int(os.getenv("PINGER_MESSAGE_ID"))

# Timezone
IST = pytz.timezone("Asia/Kolkata")
START_TIME = datetime.now(timezone.utc)

# Discord bot setup
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ----------- FLASK APP & WEBHOOK ----------- #
app = Flask("")

@app.route("/")
def home():
    # Serves the status page
    try:
        return send_from_directory("static", "bot_status.html")
    except Exception:
        return "Bot is Online (static/bot_status.html missing)"

# Merged Feature: Uploader Bot Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    channel_id = int(data.get("channel_id"))
    file_id = int(data.get("file_id"))

    # Use the running bot to fetch the URL safely
    if not bot.is_ready():
        return jsonify({"error": "Bot not ready"}), 503

    future = asyncio.run_coroutine_threadsafe(fetch_cdn_url(channel_id, file_id), bot.loop)
    try:
        cdn_url = future.result(timeout=10) # 10s timeout
        return jsonify({"cdn_url": cdn_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

async def fetch_cdn_url(channel_id, file_id):
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            # Try fetching if not in cache
            try:
                channel = await bot.fetch_channel(channel_id)
            except:
                return None
        
        message = await channel.fetch_message(file_id)
        if message.attachments:
            return message.attachments[0].url
        return None
    except Exception as e:
        print(f"❌ Webhook Fetch Error: {e}")
        return None

def run_flask():
    # Binds to the Render PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ----------- PINGER LOGIC ----------- #

RENDER_BOTS = {
    "3 IN ONE": "https://dc-all-bot.onrender.com",
    "NRE UPLODER": "https://nre-uploader-bot.onrender.com",
    "nremods.com": "https://nremods.onrender.com/",
    "CoupleWalls": "https://couplewalls.onrender.com",    
    "Divine Bot (A S)": "https://divine-bot-2vp1.onrender.com/",
    "epicflacmusic": "https://epicflacmusic.onrender.com/",
    "pin fetch": "https://autocad-education.onrender.com/",
}
bot_statuses = {name: "🔄 CHECKING..." for name in RENDER_BOTS}

@tasks.loop(seconds=10)
async def update_uptime_embed():
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel: return

        try:
            message = await channel.fetch_message(MESSAGE_ID)
        except discord.NotFound: return

        now = datetime.now(IST)
        # Fix: Ensure START_TIME is aware before subtracting
        start_ist = START_TIME.astimezone(IST)
        uptime = now - start_ist
        
        if uptime.total_seconds() < 0:
            uptime = timedelta(seconds=0)

        uptime_str = str(uptime).split('.')[0] # Cleaner formatting
        
        status_lines = [f"{name.ljust(20)} ```{status}```" for name, status in bot_statuses.items()]
        status_block = "\n".join(status_lines)

        embed = discord.Embed(title="🟢 UPTIME MONITOR", color=discord.Color.green())
        embed.description = (
            f"START       ```{start_ist.strftime('%I:%M:%S %p')}```\n"
            f"UPTIME      ```{uptime_str}```\n"
            f"LAST UPDATE ```{now.strftime('%I:%M:%S %p')}```\n\n"
            f"{status_block}"
        )
        await message.edit(embed=embed)

    except Exception as e:
        print(f"❌ Embed Update Error: {e}")

@tasks.loop(seconds=60)
async def ping_render_urls():
    async with aiohttp.ClientSession() as session:
        for name, url in RENDER_BOTS.items():
            try:
                async with session.get(url, timeout=10) as response:
                    bot_statuses[name] = "ONLINE" if response.status == 200 else "OFFLINE"
            except:
                bot_statuses[name] = "OFFLINE"

# Watchdog to keep tasks alive
@tasks.loop(minutes=1)
async def watchdog():
    if not update_uptime_embed.is_running():
        update_uptime_embed.start()
    if not ping_render_urls.is_running():
        ping_render_urls.start()

# Helper Command
@bot.tree.command(name="saym", description="Send a dummy embed")
@app_commands.describe(channel="Channel to send to")
@app_commands.checks.has_any_role("ROOT", "MOD")
async def saym(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="📦 Dummy Embed", description="Sample embed.", color=discord.Color.purple())
    await channel.send(embed=embed)
    await interaction.followup.send(f"✅ Sent to {channel.mention}")

@bot.event
async def on_ready():
    print(f"✅ PINGER & WEBHOOK Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="Servers & Uploads 💘⚙️"
    ))
    await bot.tree.sync()
    
    # Start Tasks
    if not ping_render_urls.is_running(): ping_render_urls.start()
    if not update_uptime_embed.is_running(): update_uptime_embed.start()
    if not watchdog.is_running(): watchdog.start()
    
    # Start Flask Server in Thread
    threading.Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    bot.run(TOKEN)
