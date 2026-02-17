import subprocess
import threading
import time
import sys
import signal
import os
from flask import Flask, send_from_directory

# ----------- Configuration ----------- #
# List your bot files here
BOT_FILES = [
    "nottherealepic.py",
    "giveawaybot.py",
    "pinger.py"
    # "divine_hall.py",
    # "epic_yt_downloader.py"
]

# Time to wait (in seconds) between starting each bot to avoid Rate Limits
STARTUP_DELAY = 15 

# ----------- Flask App ----------- #
app = Flask("")

@app.route("/")
def home():
    # Serves the status page (make sure the file exists in /static)
    return send_from_directory("static", "bot_status.html")

def run_flask():
    # Use os.environ.get to play nice with Render's port assignment
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ----------- Process Manager ----------- #
processes = []

def start_bot(filename):
    """Starts a bot using the current Python interpreter."""
    print(f"[SYSTEM] 🚀 Launching {filename}...")
    # sys.executable ensures we use the exact same Python environment
    proc = subprocess.Popen([sys.executable, filename])
    processes.append(proc)

def cleanup_processes(signum, frame):
    """Kills all subprocesses when the main script is stopped."""
    print("\n[SYSTEM] 🛑 Shutting down all bots...")
    for proc in processes:
        if proc.poll() is None:  # If process is still running
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    print("[SYSTEM] All bots stopped. Exiting.")
    sys.exit(0)

# ----------- Main Execution ----------- #
if __name__ == "__main__":
    # 1. Register signal handlers (Detects Stop/Restart commands from Render)
    signal.signal(signal.SIGINT, cleanup_processes)
    signal.signal(signal.SIGTERM, cleanup_processes)

    # 2. Start Flask server in a separate thread
    print("[SYSTEM] Starting Web Server...")
    threading.Thread(target=run_flask, daemon=True).start()

    # 3. Start Bots with a Delay (The Fix for 429 Errors)
    print(f"[SYSTEM] Starting {len(BOT_FILES)} bots with a {STARTUP_DELAY}s delay...")
    
    for bot_file in BOT_FILES:
        start_bot(bot_file)
        time.sleep(STARTUP_DELAY)  # <--- CRITICAL: Waits before starting the next one

    print("[SYSTEM] ✅ All bots launched. Monitoring...")

    # 4. Keep the main thread alive
    try:
        while True:
            time.sleep(60)
            # Optional: Check if bots are still running here
    except KeyboardInterrupt:
        cleanup_processes(None, None)
