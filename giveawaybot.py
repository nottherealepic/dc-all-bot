# === PATCH for Python 3.13.4 (no audio use) ===
import sys, types
sys.modules['audioop'] = types.SimpleNamespace()

# === Imports ===
import os
import random
import asyncio
import pytz
import asyncpg
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone

# === Intents & Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# === Env Config ===
SERVER_NAME       = os.getenv("SERVER_NAME", "MyServer")
TOKEN             = os.getenv("BOT_TOKEN")               # your bot token
DATABASE_URL      = os.getenv("DATABASE_URL")            # postgres://user:pass@host:port/db
STATUS_CHANNEL_ID = int(os.getenv("STATUS_CHANNEL_ID", 0))  # channel that holds uptime embed
UPTIME_MSG_ID     = int(os.getenv("UPTIME_MSG_ID", 0))      # existing message to edit for uptime

if not TOKEN:
    print("❌ BOT TOKEN missing in environment variables (BOT_TOKEN)!")
    raise SystemExit(1)
if not DATABASE_URL:
    print("❌ DATABASE_URL missing in environment variables!")
    raise SystemExit(1)

bot = commands.Bot(command_prefix="!", intents=intents)

# === Timezone & Uptime Tracking ===
tz = pytz.timezone("Asia/Kolkata")
start_time = datetime.now(tz)
status_message = None

# === PostgreSQL Pool (set in on_ready) ===
db_pool: asyncpg.Pool | None = None

# === Helpers ===
def format_uptime(delta: timedelta) -> str:
    """Pretty format a timedelta as DD:HH:MM:SS."""
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days:02}d:{hours:02}h:{minutes:02}m:{seconds:02}s"

async def init_db(pool: asyncpg.Pool) -> None:
    """Create tables if they don't exist (runs once at startup)."""
    async with pool.acquire() as conn:
        # Use TIMESTAMPTZ to store timezone-aware UTC datetimes
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS giveaways (
            id SERIAL PRIMARY KEY,
            message_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            end_time TIMESTAMPTZ NOT NULL,
            prize TEXT,
            winners_count INT NOT NULL,
            host_id BIGINT NOT NULL,
            ended BOOLEAN DEFAULT FALSE
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            giveaway_id INT REFERENCES giveaways(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            PRIMARY KEY (giveaway_id, user_id)
        );
        """)
        # Helpful indexes for performance at scale
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_giveaways_end ON giveaways (ended, end_time);")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_participants_gid ON participants (giveaway_id);")

# === Task: Update uptime message ===
@tasks.loop(seconds=20)
async def update_uptime():
    """Updates the bot's uptime embed every 20 seconds."""
    global status_message
    now = datetime.now(tz)
    uptime = format_uptime(now - start_time)
    last_update = now.strftime("%I:%M:%S %p IST")
    started = start_time.strftime("%I:%M %p IST")

    embed = discord.Embed(title=f"🎉 {SERVER_NAME} Giveaway Bot", color=discord.Color.green())
    embed.add_field(name="START", value=f"```{started}```", inline=False)
    embed.add_field(name="UPTIME", value=f"```{uptime}```", inline=False)
    embed.add_field(name="LAST UPDATE", value=f"```{last_update}```", inline=False)

    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        return
    try:
        if not status_message and UPTIME_MSG_ID:
            status_message = await channel.fetch_message(UPTIME_MSG_ID)
        if status_message:
            await status_message.edit(embed=embed)
    except Exception as e:
        print(f"❌ Uptime update error: {e}")

# === Role Check Decorator ===
def has_required_role():
    """Allows only users with 'root' or 'mod' roles to run the command."""
    async def predicate(interaction: discord.Interaction) -> bool:
        allowed_roles = {"root", "mod"}
        user_roles = {role.name.lower() for role in interaction.user.roles}
        return not allowed_roles.isdisjoint(user_roles)
    return app_commands.check(predicate)

# === Giveaway Join Button View ===
class GiveawayView(discord.ui.View):
    """A persistent view with a button to enter the giveaway."""
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        """On click, add the user as a participant (idempotent)."""
        if db_pool is None:
            return await interaction.response.send_message("DB not ready. Try again.", ephemeral=True)
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO participants (giveaway_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                self.giveaway_id, interaction.user.id
            )
        await interaction.response.send_message("✅ You're in!", ephemeral=True)

# === Slash Command: Start Giveaway ===
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
async def epicgiveaway(
    interaction: discord.Interaction,
    title: str,
    sponsor: str,
    duration: int,
    item: str,
    winners: int,
    channel: discord.TextChannel
):
    """
    Creates a giveaway embed with a 'Enter' button.
    Stores it in the DB and schedules auto-ending via background task.
    """
    await interaction.response.send_message(f"🎉 Giveaway started in {channel.mention}!", ephemeral=True)

    # Use timezone-aware UTC time (Python 3.13+ safe)
    end_time_utc = datetime.now(timezone.utc) + timedelta(minutes=duration)

    embed = discord.Embed(title=f"🎉 {title} 🎉", color=discord.Color.blurple())
    embed.add_field(name="🎁 Item", value=item, inline=False)
    embed.add_field(name="🏆 Winners", value=str(winners), inline=True)
    # Show IST to users, store UTC in DB
    embed.add_field(
        name="🕒 Ends",
        value=end_time_utc.astimezone(tz).strftime("%d %b %Y, %I:%M %p IST"),
        inline=True
    )
    embed.add_field(name="👤 Hosted by", value=sponsor, inline=False)
    embed.set_footer(text=f"Started by {interaction.user.display_name}")
    embed.timestamp = discord.utils.utcnow()

    msg = await channel.send(embed=embed)

    # Save giveaway and attach a persistent view
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO giveaways (message_id, channel_id, end_time, prize, winners_count, host_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            msg.id, channel.id, end_time_utc, item, winners, interaction.user.id
        )
    view = GiveawayView(row["id"])
    await msg.edit(view=view)

# === Slash Command: Send Test Embed ===
@bot.tree.command(name="say", description="Send dummy embed to a channel")
@has_required_role()
@app_commands.describe(channel="Channel to send embed")
async def say(interaction: discord.Interaction, channel: discord.TextChannel):
    """Sends a simple embed to verify bot messaging works."""
    embed = discord.Embed(
        title="📢 Dummy Embed",
        description="This is a test embed.",
        color=discord.Color.orange()
    )
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Sent to {channel.mention}", ephemeral=True)

# === Background Giveaway Checker ===
@tasks.loop(seconds=30)
async def check_giveaways():
    """Ends giveaways that reached end_time, picks winners, and updates the message."""
    if db_pool is None:
        return
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

            participants = await conn.fetch(
                "SELECT user_id FROM participants WHERE giveaway_id = $1",
                giveaway_id
            )
            user_ids = [p["user_id"] for p in participants]

            channel = bot.get_channel(channel_id)
            if not channel:
                # Mark ended to avoid infinite retries on missing channel
                await conn.execute("UPDATE giveaways SET ended = TRUE WHERE id = $1", giveaway_id)
                continue

            try:
                msg = await channel.fetch_message(message_id)
            except discord.NotFound:
                await conn.execute("UPDATE giveaways SET ended = TRUE WHERE id = $1", giveaway_id)
                continue

            result_embed = discord.Embed(title="🎉 Giveaway Ended!", color=discord.Color.red())
            result_embed.add_field(name="🎁 Prize", value=prize or "Unknown", inline=False)

            if len(user_ids) < max(1, winners_count):
                result_embed.add_field(name="❌ Result", value="Not enough participants", inline=False)
            else:
                # Pick unique winners
                winners = random.sample(user_ids, min(winners_count, len(user_ids)))
                mentions = ", ".join(f"<@{uid}>" for uid in winners)
                result_embed.add_field(name="🏆 Winner(s)", value=mentions, inline=False)

            result_embed.set_footer(text="Ended via auto-check")
            await msg.edit(embed=result_embed, view=None)
            await conn.execute("UPDATE giveaways SET ended = TRUE WHERE id = $1", giveaway_id)

# === Events ===
@bot.event
async def on_connect():
    """Reset uptime start when (re)connecting."""
    global start_time
    start_time = datetime.now(tz)

@bot.event
async def on_ready():
    """Initialize DB, sync commands, start tasks, set presence."""
    global db_pool
    print("🔌 Connecting PostgreSQL pool...")
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    await init_db(db_pool)
    print("✅ Connected to PostgreSQL & ensured tables.")

    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Coded by NotTheRealEpic"))

    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} application command(s).")
    except Exception as e:
        print(f"⚠️ Slash command sync failed: {e}")

    # Start background loops
    update_uptime.start()
    check_giveaways.start()

# === Run Bot ===
if __name__ == "__main__":
    bot.run(TOKEN)
