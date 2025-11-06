import discord
from discord import app_commands
from discord.ext import commands
import psycopg2
import os
from dotenv import load_dotenv

# ------------------- CONFIG from .env -------------------
load_dotenv()
TOKEN = os.environ.get("DISCORD_TOKEN_HOS")
ALLOWED_ROLE = os.environ.get("ALLOWED_ROLE_HOS", "Leaderboard Moderator")
DATABASE_URL = os.environ.get("DATABASE_URL_HOS")
LINEUP_CHANNEL_ID = os.environ.get("LINEUP_CHANNEL_ID_HOS")
LINEUP_MESSAGE_ID = os.environ.get("LINEUP_MESSAGE_ID_HOS")

if not TOKEN or not DATABASE_URL:
    raise ValueError("DISCORD_TOKEN and DATABASE_URL must be set in your .env file.")

# ------------------- BOT & DATABASE SETUP -------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Establish a persistent connection to the database
try:
    conn = psycopg2.connect(DATABASE_URL)
    print("Database connection established successfully.")
except psycopg2.OperationalError as e:
    raise ConnectionError(f"Could not connect to the database: {e}") from e


# ------------------- HELPERS & DECORATORS -------------------

# Custom check decorator for moderator role
def is_mod():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False # Cannot check roles in DMs
        
        has_permission = discord.utils.get(interaction.user.roles, name=ALLOWED_ROLE) is not None
        if not has_permission:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return has_permission
    return app_commands.check(predicate)

# Central function to update the main lineup embed
async def update_lineup_message():
    if not LINEUP_CHANNEL_ID or not LINEUP_MESSAGE_ID:
        print("Warning: LINEUP_CHANNEL_ID or LINEUP_MESSAGE_ID not set. Run /setup_lineup and configure .env.")
        return

    try:
        channel = await bot.fetch_channel(int(LINEUP_CHANNEL_ID))
        message = await channel.fetch_message(int(LINEUP_MESSAGE_ID))
    except (discord.NotFound, discord.Forbidden, ValueError):
        print("Error: Could not find the channel or message specified in .env. Please re-run /setup_lineup.")
        return

    embed = discord.Embed(
        title="THE DEFECTIVE LINEUP", 
        color=0xff0000, 
        timestamp=discord.utils.utcnow()
    )
    
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, name FROM categories ORDER BY name;")
        categories = cursor.fetchall()
        
        if not categories:
            embed.description = "No categories exist yet. Use `/add_category` to start."
        else:
            for cat_id, cat_name in categories:
                cursor.execute(
                    "SELECT rank, player_name, user_id, comment FROM entries WHERE category_id=%s ORDER BY rank;", 
                    (cat_id,)
                )
                entries = cursor.fetchall()
                
                text = ""
                if not entries:
                    text = "*No entries yet.*"
                else:
                    for rank, player_name, user_id, comment in entries:
                        user_mention = f"<@{user_id}>" if user_id else ""
                        comment_text = f" - *{comment}*" if comment else ""
                        text += f"`#{rank}` **{player_name}** {user_mention}{comment_text}\n"

                embed.add_field(name=f"🏆 {cat_name}", value=text, inline=False)

    embed.set_footer(text="Last Updated")
    await message.edit(embed=embed)
    print("Lineup message updated successfully.")

# ------------------- BOT EVENTS -------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")
    await update_lineup_message() # Update the message on startup

# ------------------- SLASH COMMANDS -------------------

# The specific user ID you want to grant access to
OWNER_ID = 891355913271771146

@bot.tree.command(name="setup_lineup", description="Creates the leaderboard message (Owner only).")
# The @is_mod() decorator has been removed.
async def setup_lineup(interaction: discord.Interaction):
    """Sends the initial embed and provides setup instructions. ONLY FOR BOT OWNER."""

    # NEW: Check if the user running the command is the owner.
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ This command can only be used by the bot owner.",
            ephemeral=True
        )
        return  # Stop the command if the user is not the owner.

    # The rest of the code is the same as before.
    embed = discord.Embed(
        title="Leaderboard Initializing...",
        description="This message will automatically update with the latest leaderboard data.",
        color=0x333333
    )
    # Send the message to the channel where the command was used
    msg = await interaction.channel.send(embed=embed)
    
    env_vars = f"LINEUP_CHANNEL_ID={msg.channel.id}\nLINEUP_MESSAGE_ID={msg.id}"
    
    await interaction.response.send_message(
        "✅ **Setup message sent!**\n\n"
        "Please add the following lines to your `.env` file and **restart the bot**:\n"
        f"```ini\n{env_vars}\n```",
        ephemeral=True
    )

@bot.tree.command(name="add_category", description="Add a new category to the leaderboard.")
@is_mod()
async def add_category(interaction: discord.Interaction, category_name: str):
    with conn.cursor() as cursor:
        cursor.execute("INSERT INTO categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING;", (category_name,))
        conn.commit()
        if cursor.rowcount > 0:
            await interaction.response.send_message(f"✅ Category **{category_name}** added.", ephemeral=True)
            await update_lineup_message()
        else:
            await interaction.response.send_message(f"⚠️ Category **{category_name}** already exists.", ephemeral=True)

@bot.tree.command(name="delete_category", description="Delete a category and all its entries.")
@is_mod()
async def delete_category(interaction: discord.Interaction, category_name: str):
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM categories WHERE name=%s RETURNING id;", (category_name,))
        if cursor.fetchone():
            conn.commit()
            await interaction.response.send_message(f"✅ Category **{category_name}** deleted.", ephemeral=True)
            await update_lineup_message()
        else:
            await interaction.response.send_message("⚠️ Category not found.", ephemeral=True)

@bot.tree.command(name="update", description="Add or update an entry in a category.")
@is_mod()
async def update(
    interaction: discord.Interaction,
    category_name: str,
    rank: app_commands.Range[int, 1, 100], # Range for rank validation
    player_name: str,
    user: discord.User = None,
    comment: str = ""
):
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM categories WHERE name=%s;", (category_name,))
        result = cursor.fetchone()
        if not result:
            return await interaction.response.send_message("⚠️ Category does not exist.", ephemeral=True)
        category_id = result[0]

        cursor.execute("""
            INSERT INTO entries (category_id, rank, player_name, user_id, comment)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (category_id, rank)
            DO UPDATE SET player_name = EXCLUDED.player_name, user_id = EXCLUDED.user_id, comment = EXCLUDED.comment;
        """, (category_id, rank, player_name, user.id if user else None, comment))
        conn.commit()

    await interaction.response.send_message(
        f"✅ Updated **{category_name}** rank #{rank} with player **{player_name}**.",
        ephemeral=True
    )
    await update_lineup_message()

@bot.tree.command(name="remove_entry", description="Remove an entry from a category.")
@is_mod()
async def remove_entry(interaction: discord.Interaction, category_name: str, rank: int):
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM categories WHERE name=%s;", (category_name,))
        result = cursor.fetchone()
        if not result:
            return await interaction.response.send_message("⚠️ Category does not exist.", ephemeral=True)
        category_id = result[0]

        cursor.execute("DELETE FROM entries WHERE category_id=%s AND rank=%s RETURNING id;", (category_id, rank))
        if cursor.fetchone():
            conn.commit()
            await interaction.response.send_message(f"✅ Removed rank #{rank} from **{category_name}**.", ephemeral=True)
            await update_lineup_message()
        else:
            await interaction.response.send_message("⚠️ Entry not found for that rank.", ephemeral=True)

# ------------------- RUN BOT -------------------
bot.run(TOKEN)
