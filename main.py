import asyncio
from flask import Flask, send_from_directory
import threading

# ----------- Flask App for Uptime -----------
app = Flask("")

@app.route("/")
def home():
    return send_from_directory("static", "bot_status.html")

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ----------- Async function to run each bot file -----------
async def run_bot(path):
    proc = await asyncio.create_subprocess_exec('python3', path)
    await proc.wait()

# ----------- Main async function to run all bots -----------
async def main():
    await asyncio.gather(
        run_bot("nottherealepic.py"),
        run_bot("giveawaybot.py"),
        run_bot("pinger.py")
    )

# ----------- Start Flask in a separate thread -----------
flask_thread = threading.Thread(target=run_flask)
flask_thread.start()

# ----------- Start the bots -----------
asyncio.run(main())
