# === PATCH for Python 3.13.4 (no audio use) ===
import sys, types
sys.modules['audioop'] = types.SimpleNamespace()

# === Imports ===
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio, random, os
from datetime import datetime, timedelta
import pytz
from threading import Thread
import asyncpg



# === Discord Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# === Timezone & Uptime ===
tz = pytz.timezone("Asia/Kolkata")
start_time = datetime.now(tz)
status_channel_id = 1391327447764435005
status_message_id = int(os.getenv("UPTIME_MSG_ID", "0"))
status_message = None

# === PostgreSQL ===
db_pool = None
DATABASE_URL = os.getenv("DATABASE_URL")  # Add this in Render env vars

# === Format Uptime ===
def format_uptime(delta):
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days:02}d:{hours:02}h:{minutes:02}m:{seconds:02}s"

@tasks.loop(seconds=20)
async def update_uptime():
    global status_message
    now = datetime.now(tz)
    uptime = format_uptime(now - start_time)
    last_update = now.strftime("%I:%M:%S %p IST")
    started = start_time.strftime("%I:%M %p IST")

    embed = discord.Embed(title="🎉 EPIC GIVEAWAY BOT", color=discord.Color.green())
    embed.add_field(name="START", value=f"```{started}```", inline=False)
    embed.add_field(name="UPTIME", value=f"```{uptime}```", inline=False)
    embed.add_field(name="LAST UPDATE", value=f"```{last_update}```", inline=False)

    channel = bot.get_channel(status_channel_id)
    if not channel:
        return
    try:
        if not status_message:
            status_message = await channel.fetch_message(status_message_id)
        await status_message.edit(embed=embed)
    except Exception as e:
        print(f"❌ Uptime update error: {e}")

# === Role Check: Only ROOT or MOD ===
def has_required_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        allowed_roles = ["root", "mod"]
        user_roles = [role.name.lower() for role in interaction.user.roles]
        return any(role in allowed_roles for role in user_roles)
    return app_commands.check(predicate)

# === Giveaway View ===
class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO participants (giveaway_id, user_id)
                VALUES ($1, $2) ON CONFLICT DO NOTHING
                """, self.giveaway_id, interaction.user.id
            )
        await interaction.response.send_message("✅ You're in!", ephemeral=True)

# === Slash Commands ===
@bot.tree.command(name="epicgiveaway", description="Start a giveaway 🎁")
@has_required_role()
@app_commands.describe(
    title="Giveaway Title",
    sponsor="Sponsor Name",
    duration="Duration in minutes",
    item="Giveaway Item",
    winners="Number of winners",
    channel="Channel to post the giveaway"
)
async def epicgiveaway(interaction: discord.Interaction,
                       title: str,
                       sponsor: str,
                       duration: int,
                       item: str,
                       winners: int,
                       channel: discord.TextChannel):
    await interaction.response.send_message(f"🎉 Giveaway started in {channel.mention}!", ephemeral=True)

    end_time = datetime.utcnow() + timedelta(minutes=duration)
    embed = discord.Embed(title=f"🎉 {title} 🎉", color=discord.Color.blurple())
    embed.add_field(name="🎁 Item", value=item, inline=False)
    embed.add_field(name="🏆 Winners", value=str(winners), inline=True)
    embed.add_field(name="🕒 Ends", value=end_time.strftime("%d %b %Y, %I:%M %p IST"), inline=True)
    embed.add_field(name="👤 Hosted by", value=sponsor, inline=False)
    embed.set_footer(text=f"Started by {interaction.user.display_name}")
    embed.timestamp = discord.utils.utcnow()

    msg = await channel.send(embed=embed)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO giveaways (message_id, channel_id, end_time, prize, winners_count, host_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            msg.id, channel.id, end_time, item, winners, interaction.user.id
        )
    view = GiveawayView(row["id"])
    await msg.edit(view=view)

@bot.tree.command(name="say", description="Send dummy embed to channel")
@has_required_role()
@app_commands.describe(channel="Channel to send embed")
async def say(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(title="📢 Dummy Embed", description="This is a test embed.", color=discord.Color.orange())
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Sent to {channel.mention}", ephemeral=True)

# === Background Giveaway Checker ===
@tasks.loop(seconds=30)
async def check_giveaways():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM giveaways WHERE end_time <= NOW() AND ended = FALSE"
        )
        for row in rows:
            message_id = row["message_id"]
            channel_id = row["channel_id"]
            giveaway_id = row["id"]
            prize = row["prize"]
            winners_count = row["winners_count"]
            host_id = row["host_id"]

            participants = await conn.fetch("SELECT user_id FROM participants WHERE giveaway_id = $1", giveaway_id)
            user_ids = [p["user_id"] for p in participants]

            channel = bot.get_channel(channel_id)
            if not channel:
                continue
            try:
                msg = await channel.fetch_message(message_id)
            except:
                continue

            embed = discord.Embed(title="🎉 Giveaway Ended!", color=discord.Color.red())
            embed.add_field(name="🎁 Prize", value=prize or "Unknown", inline=False)
            if len(user_ids) < winners_count:
                embed.add_field(name="❌ Result", value="Not enough participants", inline=False)
            else:
                winners = random.sample(user_ids, winners_count)
                mentions = ", ".join(f"<@{uid}>" for uid in winners)
                embed.add_field(name="🏆 Winner(s)", value=mentions, inline=False)

            embed.set_footer(text="Ended via auto-check")
            await msg.edit(embed=embed, view=None)
            await conn.execute("UPDATE giveaways SET ended = TRUE WHERE id = $1", giveaway_id)

# === Events ===
@bot.event
async def on_connect():
    global start_time
    start_time = datetime.now(tz)

@bot.event
async def on_ready():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    print("✅ Connected to PostgreSQL")
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} commands.")
    except Exception as e:
        print(f"⚠️ Sync failed: {e}")
    update_uptime.start()
    check_giveaways.start()

# === Run the Bot ===
if __name__ == "__main__":
    TOKEN = os.getenv("BABU")
    if not TOKEN:
        print("❌ BOT TOKEN not found (env: BABU)")
        exit()
    bot.run(TOKEN)
