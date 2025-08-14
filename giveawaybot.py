import sys, types
sys.modules['audioop'] = types.SimpleNamespace()

import os
import random
import asyncio
import pytz
import asyncpg
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, timezone

SERVER_NAME       = os.getenv("SERVER_NAME", "MyServer")
TOKEN             = os.getenv("BOT_TOKEN")
DATABASE_URL      = os.getenv("DATABASE_URL")
STATUS_CHANNEL_ID = int(os.getenv("STATUS_CHANNEL_ID", 0))
UPTIME_MSG_ID     = int(os.getenv("UPTIME_MSG_ID", 0))
ADMIN_ROLES       = {r.strip().lower() for r in os.getenv("ADMIN_ROLES", "").split(",") if r.strip()}
print("Loaded admin roles:", ADMIN_ROLES)  

if not TOKEN or not DATABASE_URL:
    raise SystemExit("❌ Missing BOT_TOKEN or DATABASE_URL in environment variables.")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

tz = pytz.timezone("Asia/Kolkata")
start_time = datetime.now(tz)
status_message = None
db_pool: asyncpg.Pool | None = None

def format_uptime(delta: timedelta) -> str:
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days:02}d:{hours:02}h:{minutes:02}m:{seconds:02}s"

async def init_db(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
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
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            giveaway_id INT REFERENCES giveaways(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            PRIMARY KEY (giveaway_id, user_id)
        )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_giveaways_end ON giveaways (ended, end_time)")
        await conn.execute("CREATE INDEX IF NOT EXISTS ix_participants_gid ON participants (giveaway_id)")

@tasks.loop(seconds=20)
async def update_uptime():
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

def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        if not ADMIN_ROLES:
            return False
        user_roles = {role.name.lower() for role in interaction.user.roles}
        return not ADMIN_ROLES.isdisjoint(user_roles)
    return app_commands.check(predicate)

class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green, custom_id="persistent_giveaway_button")
    async def enter_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if db_pool is None:
            return await interaction.response.send_message("DB not ready. Try again.", ephemeral=True)
        async with db_pool.acquire() as conn:
            # Check if giveaway has ended
            giveaway = await conn.fetchrow("SELECT ended FROM giveaways WHERE id = $1", self.giveaway_id)
            if giveaway and giveaway['ended']:
                await interaction.response.send_message("Sorry, this giveaway has already ended.", ephemeral=True)
                return

            await conn.execute("""
                INSERT INTO participants (giveaway_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
            """, self.giveaway_id, interaction.user.id)
        await interaction.response.send_message("✅ You're in!", ephemeral=True)

@bot.tree.command(name="epicgiveaway", description="Start a giveaway 🎁")
@is_admin()
@app_commands.describe(title="Giveaway Title", sponsor="Sponsor Name", duration="Duration in minutes", item="Giveaway Item", winners="Number of winners", channel="Channel to post the giveaway")
async def epicgiveaway(interaction: discord.Interaction, title: str, sponsor: str, duration: int, item: str, winners: int, channel: discord.TextChannel):
    await interaction.response.send_message(f"🎉 Giveaway started in {channel.mention}!", ephemeral=True)
    end_time_utc = datetime.now(timezone.utc) + timedelta(minutes=duration)

    embed = discord.Embed(title=f"🎉 {title} 🎉", color=discord.Color.blurple())
    embed.add_field(name="🎁 Item", value=item, inline=False)
    embed.add_field(name="🏆 Winners", value=str(winners), inline=True)
    embed.add_field(name="🕒 Ends", value=f"<t:{int(end_time_utc.timestamp())}:R>", inline=True)
    embed.add_field(name="👤 Hosted by", value=sponsor, inline=False)
    embed.set_footer(text=f"Started by {interaction.user.display_name}")
    embed.timestamp = discord.utils.utcnow()

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO giveaways (message_id, channel_id, end_time, prize, winners_count, host_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """, 0, channel.id, end_time_utc, item, winners, interaction.user.id)
        
        giveaway_id = row['id']
        view = GiveawayView(giveaway_id)
        msg = await channel.send(embed=embed, view=view)
        
        # Update the message_id in the database now that we have it
        await conn.execute("UPDATE giveaways SET message_id = $1 WHERE id = $2", msg.id, giveaway_id)

@bot.tree.command(name="dt", description="List all database tables")
@is_admin()
async def dt(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    table_list = "\n".join([t["table_name"] for t in tables]) or "No tables found."
    await interaction.response.send_message(f"**Tables:**\n```\n{table_list}\n```", ephemeral=True)

@bot.tree.command(name="view", description="View table data")
@is_admin()
@app_commands.describe(tablename="Name of the table to view")
async def view_table(interaction: discord.Interaction, tablename: str):
    async with db_pool.acquire() as conn:
        try:
            rows = await conn.fetch(f"SELECT * FROM {tablename} LIMIT 20")
        except Exception as e:
            return await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
    if not rows:
        await interaction.response.send_message("No data found.", ephemeral=True)
    else:
        output = "\n".join([str(dict(r)) for r in rows])
        await interaction.response.send_message(f"**First 20 rows of `{tablename}`:**\n```\n{output}\n```", ephemeral=True)

# --- NEW COMMAND ADDED ---
@bot.tree.command(name="get_msg_id", description="Sends a placeholder message and returns its ID.")
@is_admin()
async def get_msg_id(interaction: discord.Interaction):
    """Sends a placeholder to the status channel and replies with the message ID."""
    await interaction.response.defer(ephemeral=True)

    if not STATUS_CHANNEL_ID:
        await interaction.followup.send(
            "❌ **Config Error:** `STATUS_CHANNEL_ID` is not set in your environment variables.",
            ephemeral=True
        )
        return

    status_channel = bot.get_channel(STATUS_CHANNEL_ID)
    if not status_channel:
        await interaction.followup.send(
            f"❌ **Error:** I can't find the channel with ID `{STATUS_CHANNEL_ID}`.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📊 Bot Status Panel",
        description="This message is managed by the bot. Do not delete.",
        color=discord.Color.dark_grey()
    )

    try:
        new_message = await status_channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send(
            f"❌ **Permission Error:** I can't send messages in {status_channel.mention}.",
            ephemeral=True
        )
        return
    
    await interaction.followup.send(
        f"✅ Message sent to {status_channel.mention}. Here is the ID for `UPTIME_MSG_ID`:"
        f"\n```\n{new_message.id}\n```"
    )
# --- END OF NEW COMMAND ---

@tasks.loop(seconds=15)
async def check_giveaways():
    if db_pool is None:
        return
    async with db_pool.acquire() as conn:
        ended_giveaways = await conn.fetch("SELECT * FROM giveaways WHERE end_time <= NOW() AND ended = FALSE")
        for row in ended_giveaways:
            giveaway_id = row["id"]
            channel = bot.get_channel(row["channel_id"])
            if not channel:
                await conn.execute("UPDATE giveaways SET ended = TRUE WHERE id = $1", giveaway_id)
                continue
            
            try:
                msg = await channel.fetch_message(row["message_id"])
            except discord.NotFound:
                await conn.execute("UPDATE giveaways SET ended = TRUE WHERE id = $1", giveaway_id)
                continue

            participants = await conn.fetch("SELECT user_id FROM participants WHERE giveaway_id = $1", giveaway_id)
            user_ids = [p["user_id"] for p in participants]
            
            result_embed = discord.Embed(title="🎉 Giveaway Ended!", color=discord.Color.red())
            result_embed.add_field(name="🎁 Prize", value=row["prize"] or "Not specified", inline=False)

            if not user_ids or len(user_ids) < row['winners_count']:
                winners_text = "Not enough participants to determine a winner."
            else:
                winners = random.sample(user_ids, k=min(row["winners_count"], len(user_ids)))
                winners_text = ", ".join(f"<@{uid}>" for uid in winners)

            result_embed.add_field(name="🏆 Winner(s)", value=winners_text, inline=False)
            result_embed.set_footer(text="Giveaway concluded.")
            
            await msg.edit(embed=result_embed, view=None)
            await conn.execute("UPDATE giveaways SET ended = TRUE WHERE id = $1", giveaway_id)

@bot.event
async def on_connect():
    global start_time
    start_time = datetime.now(tz)

@bot.event
async def on_ready():
    global db_pool
    print("🔌 Connecting to PostgreSQL...")
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
        await init_db(db_pool)
        print("✅ Connected to PostgreSQL & ensured tables.")
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return

    # Add persistent view for giveaways
    view = GiveawayView(giveaway_id=0) # We don't need a specific ID here, just the button structure
    bot.add_view(view, message_id=None) # The custom_id will handle routing

    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Managing Giveaways | Coded by NotTheRealEpic"))
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} application command(s).")
    except Exception as e:
        print(f"⚠️ Slash command sync failed: {e}")
    
    if STATUS_CHANNEL_ID and UPTIME_MSG_ID:
        update_uptime.start()
    check_giveaways.start()

if __name__ == "__main__":
    bot.run(TOKEN)
