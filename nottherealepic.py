import os
import sys
import time
import random
import logging
import unicodedata
import discord
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from discord import app_commands, Embed

# ----------- Custom Data Imports -----------
# Make sure these files exist in your folder!
try:
    from files import files_data
    from pro_file_info import pro_file_info
    from paid_id import paid_id_data
    from licence import license_descriptions
except ImportError as e:
    logging.critical(f"❌ Missing data file: {e}")
    sys.exit(1)

# ----------- Configuration -----------
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')

TOKEN = os.getenv("asmr")  # Ensure this matches your Env Variable
UPTIME_CHANNEL_ID = 1369435929604784262
UPTIME_MSG_ID = 1391327711926157463

LEGIT_REACTION_CHANNEL_ID = 1233843778754838679
LEGIT_REACTION_MESSAGE_ID = 1404085986098413640
LEGIT_REACTION_ROLE_ID = 1232213167480901713
LEGIT_REACTION_EMOJI = "✅"
LEGIT_REACTION_GIF = "https://cdn.discordapp.com/attachments/1233831270866227271/1404083666791039079/nre_animated_low_mb.gif"

TARGET_ROLE_NAME = "LEGIT"
TIME_LIMIT_MINUTES = 180  # Hit-and-run threshold

# ----------- Bot Setup -----------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
start_time = datetime.now(timezone.utc)

# ----------- Globals & Utils -----------
user_activity = {}
user_message_tracker = defaultdict(list)

statuses = [
    "Playing GTA 6 — don't ask.", "Modding GTA like it's a career.",
    "ZModeler: cracked, patched, broken.", "Scripting when I feel like it.",
    "Helping, but not politely.", "Banning you next, probably.",
    "Discord mod — not your therapist.", "Fixing what Rockstar couldn’t."
]

bad_words = [
    "free nitro", "free nude", "sex", "onlyfans", "steam giveaway", "free robux",
    "discordnitro", "steamcommunity-", "epicgames-", "nitro-gift"
]

def normalize_text(text):
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()

def is_admin_or_mod(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator: return True
    user_roles = [r.name.upper() for r in interaction.user.roles]
    return any(r in ["ROOT", "MOD"] for r in user_roles)

def generate_code():
    return f"epic{random.randint(1, 9999):04d}"

def check_restart_limit():
    """Prevents rapid restart loops."""
    try:
        path = "last_restart.txt"
        current_time = time.time()
        if os.path.exists(path):
            with open(path, "r") as f:
                last_time = float(f.read().strip())
            if current_time - last_time < 900:  # 15 mins
                logging.warning("⛔ Restarted too quickly.")
        with open(path, "w") as f:
            f.write(str(current_time))
    except Exception:
        pass

check_restart_limit()

# ----------- Autocomplete -----------
async def model_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=m, value=m) for m in files_data if current.lower() in m.lower()][:25]

async def code_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=c, value=c) for c in paid_id_data if current.lower() in c.lower()][:25]

async def fid_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=f, value=f) for f in pro_file_info if current.lower() in f.lower()][:25]

# ----------- COMMANDS -----------

@bot.tree.command(name="pass", description="Get info & password for Mod file")
@app_commands.describe(modelname="File Name")
@app_commands.autocomplete(modelname=model_autocomplete)
@app_commands.checks.has_role("LEGIT")
async def pass_command(interaction: discord.Interaction, modelname: str):
    if modelname not in files_data:
        await interaction.response.send_message("❌ Model not found!", ephemeral=True)
        return

    data = files_data[modelname]
    desc = license_descriptions.get(data["license"], "N/A")

    embed = Embed(title=f"Access: {modelname}", color=0x2ecc71)
    embed.add_field(name="FILE NAME", value=f"```{modelname}```", inline=False)
    embed.add_field(name="VERSION", value=f"```{data.get('version', 'N/A')}```", inline=True)
    embed.add_field(name="SIZE", value=f"```{data.get('size', 'N/A')}```", inline=True)
    embed.add_field(name="LICENSE", value=f"```{data['license']}```", inline=True)
    embed.add_field(name="DETAILS", value=f"```{desc}```", inline=False)
    embed.add_field(name="PASSWORD", value=f"```{data['password']}```", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="code", description="Generate unique code (ROOT only)")
@app_commands.checks.has_role("ROOT")
async def code_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    new_code = generate_code()
    
    # Simple file append
    with open("generated_codes.txt", "a") as f:
        f.write(f"{new_code}\n")
        
    await interaction.followup.send(f"✅ Generated Code: `{new_code}`")

@bot.tree.command(name="paid_id", description="Customer info lookup (ROOT only)")
@app_commands.describe(code="Customer Code")
@app_commands.autocomplete(code=code_autocomplete)
@app_commands.checks.has_role("ROOT")
async def paid_id_command(interaction: discord.Interaction, code: str):
    if code not in paid_id_data:
        await interaction.response.send_message("❌ Code not found.", ephemeral=True)
        return

    data = paid_id_data[code]
    embed = Embed(title=f"Customer: {code}", color=0x3498db)
    for key, val in data.items():
        embed.add_field(name=key.upper(), value=f"```{val}```", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="proinfo", description="Get info about paid files (LEGIT only)")
@app_commands.autocomplete(fid=fid_autocomplete)
@app_commands.checks.has_role("LEGIT")
async def proinfo_command(interaction: discord.Interaction, fid: str):
    if fid not in pro_file_info:
        await interaction.response.send_message("❌ File ID not found.", ephemeral=True)
        return

    data = pro_file_info[fid]
    await interaction.response.defer(ephemeral=False)
    
    # Send parts sequentially
    for key in ['FIRST', 'SEC', 'THIRD', 'FOUR']:
        if data.get(key):
            await interaction.followup.send(data[key])

@bot.tree.command(name="spread", description="Announce message to channel")
@app_commands.checks.has_role("ROOT")
async def spread(interaction: discord.Interaction, channel_id: str, message: str):
    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send(message)
            await interaction.response.send_message(f"✅ Sent to {channel.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Invalid Channel ID", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"⚠️ Error: {e}", ephemeral=True)

@bot.tree.command(name="epicembed", description="Send custom embed")
@app_commands.checks.has_role("ROOT")
async def epicembed(interaction: discord.Interaction, channel_id: str, description: str, title: str = None, color: str = "#3498db"):
    try:
        channel = bot.get_channel(int(channel_id))
        col_val = int(color.lstrip("#"), 16)
        embed = Embed(title=title, description=description, color=col_val)
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Embed Sent!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"⚠️ Error: {e}", ephemeral=True)

@bot.tree.command(name="paymentxx", description="Confirm purchase")
@app_commands.checks.has_role("ROOT")
async def paymentxx(interaction: discord.Interaction, channelid: str, userid: str, spawncode: str):
    try:
        channel = await bot.fetch_channel(int(channelid))
        user = await bot.fetch_user(int(userid))
        
        msg = (f"{user.mention}\nThanks for your purchase!\n"
               f"If you need support, mention spawn code `{spawncode}` in <#1240335393686290514>.\n"
               f"— NOTTHEREALEPIC Team")
        
        await channel.send(msg)
        try:
            await user.send(f"✅ **Purchase Confirmed!**\n\n{msg}")
        except:
            pass
        await interaction.response.send_message("✅ Confirmation sent.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="warntt", description="Ticket inactivity warning")
@app_commands.checks.has_role("ROOT")
async def warntt(interaction: discord.Interaction, channelid: str, userid: str):
    try:
        channel = await bot.fetch_channel(int(channelid))
        user = await bot.fetch_user(int(userid))
        
        msg = (f"## Ticket Inactivity Warning\nHey {user.mention}, this ticket will close in 3 hours if no response.\n"
               "— NOTTHEREALEPIC Team")
        
        await channel.send(msg)
        try:
            await user.send(msg)
        except:
            pass
        await interaction.response.send_message("✅ Warning sent.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="dm", description="DM a user by ID")
@app_commands.check(is_admin_or_mod)
async def dm(interaction: discord.Interaction, userid: str, message: str):
    try:
        user = await bot.fetch_user(int(userid))
        await user.send(message.replace("\\n", "\n"))
        await interaction.response.send_message(f"✅ DM sent to {user.name}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

# ----------- EVENTS & TASKS -----------

@bot.event
async def on_ready():
    logging.info(f"✅ {bot.user} is ONLINE.")
    try:
        # Syncing globally or to specific guild (Uncomment guild for faster testing)
        await bot.tree.sync(guild=discord.Object(id=1232208366735196283))
        logging.info("✅ Commands Synced.")
    except Exception as e:
        logging.error(f"Sync Error: {e}")

    # Start loops
    if not change_status.is_running(): change_status.start()
    if not update_uptime_embed.is_running(): update_uptime_embed.start()
    if not spam_cleanup.is_running(): spam_cleanup.start()

    # Reaction Role Setup
    channel = bot.get_channel(LEGIT_REACTION_CHANNEL_ID)
    if channel:
        try:
            msg = await channel.fetch_message(LEGIT_REACTION_MESSAGE_ID)
            embed = Embed(
                title="🎯 Get Verified Access",
                description=f"React with {LEGIT_REACTION_EMOJI} to get the **Legit** role.",
                color=discord.Color.red()
            )
            embed.set_image(url=LEGIT_REACTION_GIF)
            embed.set_footer(text="Auto-Verification")
            await msg.edit(embed=embed)
            await msg.add_reaction(LEGIT_REACTION_EMOJI)
        except Exception:
            logging.warning("⚠️ Could not refresh reaction role message.")

@tasks.loop(seconds=60)
async def change_status():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=random.choice(statuses)))

@tasks.loop(seconds=50)
async def update_uptime_embed():
    try:
        channel = bot.get_channel(UPTIME_CHANNEL_ID)
        if not channel: return
        msg = await channel.fetch_message(UPTIME_MSG_ID)
        
        now = datetime.now(timezone.utc)
        ist_now = now + timedelta(hours=5, minutes=30)
        uptime = now - start_time
        
        embed = Embed(title="NOTTHEREALEPIC BOT", color=discord.Color.green())
        embed.add_field(name="STATUS", value="```ONLINE```", inline=True)
        embed.add_field(name="LAST UPDATED", value=f"```{ist_now.strftime('%H:%M:%S')} IST```", inline=True)
        embed.set_footer(text="Auto-updated every 50s")
        
        await msg.edit(embed=embed)
    except Exception:
        pass

@tasks.loop(minutes=30)
async def spam_cleanup():
    """UPGRADE: Cleans up old spam tracking data to save memory."""
    user_message_tracker.clear()

@bot.event
async def on_message(message):
    if message.author.bot: return

    # Spam & Bad Word Filter
    content = normalize_text(message.content)
    uid = message.author.id
    
    # 1. Check Bad Words
    if any(w in content for w in bad_words):
        try:
            await message.delete()
            await message.author.timeout(timedelta(hours=12), reason="Scam/NSFW")
            await message.channel.send(f"⚠️ {message.author.mention} flagged for suspicious content.", delete_after=5)
        except: pass
        return

    # 2. Check Spam (5 servers in 10 mins)
    now = datetime.now(timezone.utc)
    user_message_tracker[uid].append((content, now, message.guild.id))
    
    # Filter old messages
    user_message_tracker[uid] = [(m, t, g) for m, t, g in user_message_tracker[uid] 
                                 if (now - t).total_seconds() < 600]
    
    unique_guilds = {g for m, t, g in user_message_tracker[uid] if m == content}
    
    if len(unique_guilds) >= 5:
        try:
            await message.author.timeout(timedelta(hours=24), reason="Multi-server Spam")
            await message.delete()
        except: pass
        return

    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.message_id == LEGIT_REACTION_MESSAGE_ID and str(payload.emoji) == LEGIT_REACTION_EMOJI:
        guild = bot.get_guild(payload.guild_id)
        if not guild: return
        
        member = guild.get_member(payload.user_id)
        role = guild.get_role(LEGIT_REACTION_ROLE_ID)
        
        if member and role and not member.bot:
            await member.add_roles(role)
            # Remove reaction
            msg = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
            await msg.remove_reaction(payload.emoji, member)
            try:
                await member.send(f"✅ Verified! You now have the **{role.name}** role.")
            except: pass

@bot.event
async def on_member_join(member):
    user_activity[member.id] = {"joined": datetime.now(timezone.utc), "got_role": False}
    try:
        await member.send("Welcome! Please read rules and verify.")
    except: pass

@bot.event
async def on_member_update(before, after):
    if after.id in user_activity:
        if any(r.id == LEGIT_REACTION_ROLE_ID for r in after.roles) and not any(r.id == LEGIT_REACTION_ROLE_ID for r in before.roles):
            user_activity[after.id]["got_role"] = True

@bot.event
async def on_member_remove(member):
    # Hit and Run Ban Logic
    if member.id in user_activity:
        data = user_activity[member.id]
        if data["got_role"]:
            joined_at = data["joined"]
            time_spent_mins = (datetime.now(timezone.utc) - joined_at).total_seconds() / 60
            
            if time_spent_mins < TIME_LIMIT_MINUTES:
                logging.info(f"🚨 Hit-and-Run Detected: {member.name}")
                try:
                    await member.guild.ban(member, reason="Hit and Run (Verified & Left quickly)")
                    # Try to DM them
                    await member.send("You were banned for 'Hit and Run' (Joining, grabbing files, and leaving immediately).")
                except: pass
        del user_activity[member.id]

@bot.event
async def on_app_command_error(interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(f"⏳ Cool down! Wait {error.retry_after:.1f}s", ephemeral=True)
    elif isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
    else:
        logging.error(f"Command Error: {error}")

if __name__ == "__main__":
    if not TOKEN:
        logging.critical("❌ TOKEN NOT FOUND")
    else:
        bot.run(TOKEN)
