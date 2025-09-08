import os
import random
import asyncio
import aiohttp
import discord
import pytz
import threading
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# Load env variables
load_dotenv()
TOKEN = os.getenv("PINGER_TOKEN")
CHANNEL_ID = int(os.getenv("PINGER_CHANNEL_ID"))
MESSAGE_ID = int(os.getenv("PINGER_MESSAGE_ID"))

# Timezone
IST = pytz.timezone("Asia/Kolkata")
START_TIME = None  # Set inside on_ready

# Discord bot setup
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)



# Render URLs with display names
RENDER_BOTS = {
    "3 IN ONE": "https://dc-all-bot.onrender.com",
    "NOTTHEREALEPIC": "https://notepicbot.onrender.com",
    "nremods.com": "https://nremods.onrender.com/",
    "BE MY VALENTINE APP": "https://be-my-valentine-app.onrender.com",
    "EPIC GIVEAWAY BOT": "https://epicgiveawaybot.onrender.com",
    "face": "https://veyonafashions.onrender.com",
    "CoupleWalls": "https://couplewalls.onrender.com",
    "file uploder bot": "https://nre-uploader-bot.onrender.com",    
}
bot_statuses = {name: "🔄 CHECKING..." for name in RENDER_BOTS}

# Update embed every 10 seconds
@tasks.loop(seconds=10)
async def update_uptime_embed():
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print("❌ Channel not found.")
            return

        try:
            message = await channel.fetch_message(MESSAGE_ID)
        except discord.NotFound:
            print("❌ Message not found.")
            return

        now = datetime.now(IST)
        uptime = now - START_TIME
        if uptime.total_seconds() < 0:
            uptime = timedelta(seconds=0)

        start_str = START_TIME.strftime("%I:%M:%S %p")
        now_str = now.strftime("%I:%M:%S %p")
        days = uptime.days
        hours, rem = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days:02}:{hours:02}:{minutes:02}:{seconds:02}"

        status_lines = [f"{name.ljust(20)} ```{status}```" for name, status in bot_statuses.items()]
        status_block = "\n".join(status_lines)

        embed = discord.Embed(title="🟢 UPTIME MONITOR", color=discord.Color.green())
        embed.description = (
            f"START         ```{start_str}```\n"
            f"UPTIME        ```{uptime_str}```\n"
            f"LAST UPDATE   ```{now_str}```\n\n"
            f"{status_block}"
        )
        await message.edit(embed=embed)

    except Exception as e:
        print(f"❌ update_uptime_embed crashed: {e}")

# Ping every URL & update status
@tasks.loop(seconds=60)
async def ping_render_urls():
    try:
        async with aiohttp.ClientSession() as session:
            for name, url in RENDER_BOTS.items():
                try:
                    async with session.get(url, timeout=5) as response:
                        if response.status == 200:
                            bot_statuses[name] = "ONLINE"
                        else:
                            bot_statuses[name] = "OFFLINE"
                except Exception:
                    bot_statuses[name] = "OFFLINE"
    except Exception as e:
        print(f"❌ ping_render_urls crashed: {e}")

# Watchdog to auto-restart tasks
@tasks.loop(minutes=1)
async def watchdog():
    if not update_uptime_embed.is_running():
        print("🔁 Restarting update_uptime_embed")
        update_uptime_embed.start()

    if not ping_render_urls.is_running():
        print("🔁 Restarting ping_render_urls")
        ping_render_urls.start()

# Permission check
@app_commands.checks.has_any_role("ROOT", "MOD")
@bot.tree.command(name="saym", description="Send a dummy embed to a specified channel")
@app_commands.describe(channel="The channel to send the dummy embed")
async def saym(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    try:
        embed = discord.Embed(
            title="📦 Dummy Embed",
            description="This is a sample embed sent by the bot.",
            color=discord.Color.purple()
        )
        embed.set_footer(text="Sent by /saym command")
        await channel.send(embed=embed)
        await interaction.followup.send(f"✅ Embed sent to {channel.mention}.")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to send embed: `{e}`")

# Handle permission error
@saym.error
async def saym_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)

# on_ready setup
@bot.event
async def on_ready():
    global START_TIME
    START_TIME = datetime.now(IST)

    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="A heart for bots, not humans... 100% synthetic love 💘⚙️"
    ))

    await bot.tree.sync()
    if not ping_render_urls.is_running():
        ping_render_urls.start()
    if not update_uptime_embed.is_running():
        update_uptime_embed.start()
    if not watchdog.is_running():
        watchdog.start()

# Start Flask and bot
bot.run(TOKEN)
