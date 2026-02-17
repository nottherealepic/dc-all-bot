import os
import sys
import time
import random
import logging
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from discord import app_commands, Embed

# Import Data (Ensure these files exist)
try:
    from files import files_data
    from pro_file_info import pro_file_info
    from paid_id import paid_id_data
    from licence import license_descriptions
except ImportError:
    print("❌ Critical: Data files missing.")
    sys.exit(1)

# ----------- SETUP -----------
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("asmr")

# Bot Config
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Global Vars
start_time = datetime.now(timezone.utc)
user_activity = {}
user_message_tracker = defaultdict(list)

# Config Constants
LEGIT_ROLE_ID = 1232213167480901713
LEGIT_CHANNEL_ID = 1233843778754838679
LEGIT_MSG_ID = 1404085986098413640
TIME_LIMIT_MINUTES = 180

# ----------- SMART SPAM PROTECTION SYSTEM -----------
class SmartCooldown:
    def __init__(self):
        self.user_limits = defaultdict(lambda: {"count": 0, "last_time": 0, "penalty_until": 0})
    
    def check(self, user_id):
        now = time.time()
        data = self.user_limits[user_id]
        
        # Check Penalty
        if now < data["penalty_until"]:
            remaining = int(data["penalty_until"] - now)
            return False, f"⛔ Cooldown: You are moving too fast! Wait {remaining}s."
        
        # Reset count if 10 seconds passed
        if now - data["last_time"] > 10:
            data["count"] = 0
            
        data["count"] += 1
        data["last_time"] = now
        
        # Logic: > 3 commands in 10 seconds = Penalty
        if data["count"] > 3:
            # Smart Penalty: Increases if they keep spamming
            penalty_duration = 10 if data["count"] == 4 else 60
            data["penalty_until"] = now + penalty_duration
            return False, f"⚠️ Slow down! You triggered a {penalty_duration}s cooldown."
            
        return True, None

spam_police = SmartCooldown()

# Decorator for commands
def smart_rate_limit():
    async def predicate(interaction: discord.Interaction):
        is_safe, msg = spam_police.check(interaction.user.id)
        if not is_safe:
            await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ----------- UTILS -----------
def normalize_text(text):
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()

bad_words = [
    "free nitro", "free nude", "sex", "onlyfans", "steam giveaway", "free robux",
    "discordnitro", "steamcommunity-", "epicgames-", "nitro-gift"
]

# ----------- COMMANDS (ALL FEATURES) -----------

# 1. PASS COMMAND
@bot.tree.command(name="pass", description="Get file password & info")
@app_commands.checks.has_role("LEGIT")
@smart_rate_limit()
async def pass_cmd(interaction: discord.Interaction, modelname: str):
    if modelname in files_data:
        d = files_data[modelname]
        desc = license_descriptions.get(d.get("license"), "N/A")
        
        embed = Embed(title=f"📂 Access: {modelname}", color=0x2ecc71)
        embed.add_field(name="File Name", value=f"`{modelname}`", inline=False)
        embed.add_field(name="Version", value=f"`{d.get('version', 'N/A')}`", inline=True)
        embed.add_field(name="Size", value=f"`{d.get('size', 'N/A')}`", inline=True)
        embed.add_field(name="Password", value=f"```yaml\n{d['password']}```", inline=False)
        embed.add_field(name="License", value=f"`{d.get('license', 'N/A')}`", inline=True)
        embed.add_field(name="Details", value=f"```{desc}```", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("❌ File not found.", ephemeral=True)

@pass_cmd.autocomplete("modelname")
async def pass_autocomplete(inter, current: str):
    return [app_commands.Choice(name=m, value=m) for m in files_data if current.lower() in m.lower()][:25]

# 2. CODE GEN
@bot.tree.command(name="code", description="Generate Customer Code (ROOT)")
@app_commands.checks.has_role("ROOT")
async def code_cmd(interaction: discord.Interaction):
    code = f"epic{random.randint(1,9999):04d}"
    with open("generated_codes.txt", "a") as f: f.write(code + "\n")
    await interaction.response.send_message(f"✅ Generated: `{code}`", ephemeral=True)

# 3. PAID ID
@bot.tree.command(name="paid_id", description="Customer Lookup (ROOT)")
@app_commands.checks.has_role("ROOT")
async def paid_id_cmd(interaction: discord.Interaction, code: str):
    if code in paid_id_data:
        d = paid_id_data[code]
        embed = Embed(title=f"👤 Customer: {code}", color=0x3498db)
        for k, v in d.items(): embed.add_field(name=k, value=f"`{v}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("❌ Not found.", ephemeral=True)

@paid_id_cmd.autocomplete("code")
async def pid_autocomplete(inter, current: str):
    return [app_commands.Choice(name=c, value=c) for c in paid_id_data if current.lower() in c.lower()][:25]

# 4. PRO INFO
@bot.tree.command(name="proinfo", description="Paid File Details")
@app_commands.checks.has_role("LEGIT")
@smart_rate_limit()
async def proinfo_cmd(interaction: discord.Interaction, fid: str):
    if fid in pro_file_info:
        await interaction.response.defer()
        d = pro_file_info[fid]
        # Send parts safely
        for k in ['FIRST', 'SEC', 'THIRD', 'FOUR']:
            if d.get(k): await interaction.followup.send(d[k])
    else:
        await interaction.response.send_message("❌ ID Not Found", ephemeral=True)

@proinfo_cmd.autocomplete("fid")
async def fid_autocomplete(inter, current: str):
    return [app_commands.Choice(name=f, value=f) for f in pro_file_info if current.lower() in f.lower()][:25]

# 5. ADMIN TOOLS
@bot.tree.command(name="spread", description="Announce message")
@app_commands.checks.has_role("ROOT")
async def spread(inter: discord.Interaction, channel_id: str, message: str):
    try:
        await (bot.get_channel(int(channel_id))).send(message)
        await inter.response.send_message("✅ Sent.", ephemeral=True)
    except: await inter.response.send_message("❌ Failed.", ephemeral=True)

@bot.tree.command(name="epicembed", description="Custom Embed")
@app_commands.checks.has_role("ROOT")
async def epicembed(inter: discord.Interaction, channel_id: str, description: str, title: str=None, color: str="#3498db"):
    try:
        embed = Embed(title=title, description=description, color=int(color.lstrip("#"), 16))
        await (bot.get_channel(int(channel_id))).send(embed=embed)
        await inter.response.send_message("✅ Sent.", ephemeral=True)
    except: await inter.response.send_message("❌ Failed.", ephemeral=True)

@bot.tree.command(name="paymentxx", description="Confirm Order")
@app_commands.checks.has_role("ROOT")
async def paymentxx(inter: discord.Interaction, channelid: str, userid: str, spawncode: str):
    try:
        u = await bot.fetch_user(int(userid))
        msg = f"{u.mention}\nPurchase Confirmed! Mention `{spawncode}` for support."
        await (bot.get_channel(int(channelid))).send(msg)
        try: await u.send(f"✅ **Confirmed!**\n{msg}")
        except: pass
        await inter.response.send_message("✅ Done.", ephemeral=True)
    except Exception as e: await inter.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="warntt", description="Inactive Warning")
@app_commands.checks.has_role("ROOT")
async def warntt(inter: discord.Interaction, channelid: str, userid: str):
    try:
        u = await bot.fetch_user(int(userid))
        msg = f"## ⚠️ Inactivity Warning\n{u.mention}, this ticket will close in 3 hours."
        await (bot.get_channel(int(channelid))).send(msg)
        try: await u.send(msg)
        except: pass
        await inter.response.send_message("✅ Done.", ephemeral=True)
    except: await inter.response.send_message("❌ Failed.", ephemeral=True)

@bot.tree.command(name="dm", description="Direct Message User")
@app_commands.checks.has_any_role("ROOT", "MOD")
async def dm(inter: discord.Interaction, userid: str, message: str):
    try:
        await (await bot.fetch_user(int(userid))).send(message.replace("\\n", "\n"))
        await inter.response.send_message("✅ Sent.", ephemeral=True)
    except: await inter.response.send_message("❌ Failed (DMs off?)", ephemeral=True)

# ----------- EVENTS -----------
@bot.event
async def on_ready():
    print(f"✅ MAIN BOT ONLINE: {bot.user}")
    # Sync Commands
    await bot.tree.sync(guild=discord.Object(id=1232208366735196283))
    
    # Start Tasks
    change_status.start()
    spam_cleanup.start()
    
    # Reaction Role Refresh
    try:
        c = bot.get_channel(LEGIT_CHANNEL_ID)
        m = await c.fetch_message(LEGIT_MSG_ID)
        if not any(str(r) == "✅" and r.me for r in m.reactions):
            await m.add_reaction("✅")
    except: pass

@tasks.loop(minutes=5)
async def change_status():
    st = random.choice([
        "Playing GTA 6 — don't ask.", "Modding GTA like it's a career.",
        "ZModeler: cracked, patched, broken.", "Helping, but not politely.",
        "Banning you next, probably.", "Discord mod — not your therapist.",
        "Fixing what Rockstar couldn’t."
    ])
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=st))

@tasks.loop(minutes=30)
async def spam_cleanup():
    """Cleans up old spam tracking data."""
    user_message_tracker.clear()

@bot.event
async def on_raw_reaction_add(p):
    if p.message_id == LEGIT_MSG_ID and str(p.emoji) == "✅":
        g = bot.get_guild(p.guild_id)
        m = g.get_member(p.user_id)
        if m and not m.bot:
            await m.add_roles(g.get_role(LEGIT_ROLE_ID))
            try:
                # Clean up reaction & DM user
                await (await bot.get_channel(p.channel_id).fetch_message(p.message_id)).remove_reaction(p.emoji, m)
                await m.send("✅ You are now Verified!")
            except: pass

@bot.event
async def on_member_join(member):
    user_activity[member.id] = {"joined": datetime.now(timezone.utc), "got_role": False}
    try: await member.send("Thank you for joining the server! Please verify.")
    except: pass

@bot.event
async def on_member_update(before, after):
    # Track when they get the LEGIT role
    if after.id in user_activity:
        if any(r.id == LEGIT_ROLE_ID for r in after.roles) and not any(r.id == LEGIT_ROLE_ID for r in before.roles):
            user_activity[after.id]["got_role"] = True

@bot.event
async def on_member_remove(member):
    # Hit and Run Logic
    if member.id in user_activity:
        data = user_activity[member.id]
        if data["got_role"]:
            joined_at = data["joined"]
            time_spent_mins = (datetime.now(timezone.utc) - joined_at).total_seconds() / 60
            
            if time_spent_mins < TIME_LIMIT_MINUTES:
                print(f"🚨 Hit-and-Run: {member.name}")
                try:
                    await member.guild.ban(member, reason="Hit and Run (Verified & Left quickly)")
                    await member.send("You were banned for 'Hit and Run' (Joining, grabbing files, and leaving immediately).")
                except: pass
        del user_activity[member.id]

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    
    # 1. Bad Word Filter
    if any(w in msg.content.lower() for w in bad_words):
        try: 
            await msg.delete()
            await msg.author.timeout(timedelta(hours=12), reason="Scam/NSFW")
        except: pass
        return

    # 2. Multi-Server Spam Check
    uid = msg.author.id
    now = datetime.now(timezone.utc)
    content = normalize_text(msg.content)
    
    user_message_tracker[uid].append((content, now, msg.guild.id))
    # Filter old
    user_message_tracker[uid] = [(m, t, g) for m, t, g in user_message_tracker[uid] if (now - t).total_seconds() < 600]
    
    unique_guilds = {g for m, t, g in user_message_tracker[uid] if m == content}
    if len(unique_guilds) >= 5:
        try:
            await msg.author.timeout(timedelta(hours=24), reason="Multi-server Spam")
            await msg.delete()
        except: pass
        return

    await bot.process_commands(msg)

if __name__ == "__main__":
    if TOKEN: bot.run(TOKEN)
