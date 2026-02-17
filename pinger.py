import os
import aiohttp
import discord
import pytz
import threading
import asyncio
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from discord import app_commands
from flask import Flask, send_from_directory, request, jsonify
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("PINGER_TOKEN")
CHANNEL_ID = int(os.getenv("PINGER_CHANNEL_ID"))
MESSAGE_ID = int(os.getenv("PINGER_MESSAGE_ID"))

# Timezone & Start Time
IST = pytz.timezone("Asia/Kolkata")
START_TIME_UTC = datetime.now(timezone.utc)

# Setup
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------- FLASK SERVER ----------- #
app = Flask("")

@app.route("/")
def home():
    try: return send_from_directory("static", "bot_status.html")
    except: return "System Online."

@app.route("/webhook", methods=["POST"])
def webhook():
    # Helper for the uploader feature
    data = request.json
    if not bot.is_ready(): return jsonify({"error": "Bot loading..."}), 503
    
    future = asyncio.run_coroutine_threadsafe(fetch_cdn_url(int(data.get("channel_id")), int(data.get("file_id"))), bot.loop)
    try:
        return jsonify({"cdn_url": future.result(timeout=10)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

async def fetch_cdn_url(cid, fid):
    try:
        channel = bot.get_channel(cid) or await bot.fetch_channel(cid)
        msg = await channel.fetch_message(fid)
        return msg.attachments[0].url if msg.attachments else None
    except: return None

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ----------- MONITOR LOGIC ----------- #
RENDER_BOTS = {
    "3 IN ONE": "https://dc-all-bot.onrender.com",
    "NRE UPLOADER": "https://nre-uploader-bot.onrender.com",
    "NRE Mods Site": "https://nremods.onrender.com/",
    "CoupleWalls": "https://couplewalls.onrender.com",    
    "Divine Bot": "https://divine-bot-2vp1.onrender.com/",
    "EpicFlacMusic": "https://epicflacmusic.onrender.com/",
    "Pin Fetch": "https://autocad-education.onrender.com/",
}
bot_statuses = {name: "🔄 INIT" for name in RENDER_BOTS}

@tasks.loop(seconds=60) 
async def ping_services():
    async with aiohttp.ClientSession() as session:
        for name, url in RENDER_BOTS.items():
            try:
                async with session.get(url, timeout=10) as resp:
                    bot_statuses[name] = "ONLINE" if resp.status == 200 else "OFFLINE"
            except:
                bot_statuses[name] = "OFFLINE"

@tasks.loop(seconds=35) # Increased to 35s to prevent Rate Limits
async def update_dashboard():
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel: return
        try: msg = await channel.fetch_message(MESSAGE_ID)
        except: return

        # Time Calc
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(IST)
        start_ist = START_TIME_UTC.astimezone(IST)
        
        uptime = now_utc - START_TIME_UTC
        d, rem = divmod(int(uptime.total_seconds()), 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        
        # Formatting for UI
        uptime_str = f"{d:02}d : {h:02}h : {m:02}m : {s:02}s"
        
        # Generate Status Block (Code Block Styling)
        status_text = ""
        for name, status in bot_statuses.items():
            icon = "🟢" if status == "ONLINE" else "🔴"
            status_text += f"{icon} {name.ljust(18)} [{status}]\n"

        # Build Embed
        embed = discord.Embed(title="🖥️ SYSTEM MONITOR", color=0x2b2d31) # Dark theme
        embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)
        
        # Row 1: Start Info
        embed.add_field(name="🚀 START TIME (IST)", value=f"```css\n{start_ist.strftime('%I:%M:%S %p')}```", inline=True)
        embed.add_field(name="📅 START DATE", value=f"```css\n{start_ist.strftime('%d-%b-%Y')}```", inline=True)
        
        # Row 2: Live Stats
        embed.add_field(name="⏳ SYSTEM UPTIME", value=f"```yaml\n{uptime_str}```", inline=True)
        embed.add_field(name="🔄 LAST REFRESH", value=f"```yaml\n{now_ist.strftime('%I:%M:%S %p')}```", inline=True)
        
        # Row 3: Services
        embed.add_field(name="📡 SERVICE STATUS", value=f"```ini\n{status_text}```", inline=False)
        
        embed.set_footer(text="Auto-refreshing every 35s • Rate Limit Protected")
        
        await msg.edit(embed=embed)
    except Exception as e:
        print(f"Dash Error: {e}")

@bot.event
async def on_ready():
    print(f"✅ MONITOR STARTED: {bot.user}")
    threading.Thread(target=run_flask, daemon=True).start()
    ping_services.start()
    update_dashboard.start()

if __name__ == "__main__":
    bot.run(TOKEN)
