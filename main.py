import subprocess
import time
import sys
import signal
import os

# ----------- Configuration ----------- #
# pinger.py MUST run first because it hosts the Web Server
BOTS = [
    {"file": "pinger.py", "delay": 0},      # Starts immediately to bind Port 8080
    {"file": "nottherealepic.py", "delay": 30}, # Waits 30s to avoid Discord Rate Limit
]

processes = []

def start_bot(bot_info):
    """Starts a bot subprocess."""
    filename = bot_info["file"]
    delay = bot_info["delay"]
    
    if delay > 0:
        print(f"[SYSTEM] ⏳ Waiting {delay}s before starting {filename}...")
        time.sleep(delay)
        
    print(f"[SYSTEM] 🚀 Launching {filename}...")
    # Uses the same Python interpreter as the main script
    proc = subprocess.Popen([sys.executable, filename])
    processes.append(proc)

def cleanup_processes(signum, frame):
    """Force kills all bots on shutdown."""
    print("\n[SYSTEM] 🛑 Shutting down all bots...")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    print("[SYSTEM] All bots stopped. Exiting.")
    sys.exit(0)

if __name__ == "__main__":
    # Register shutdown signals (CRITICAL for Render)
    signal.signal(signal.SIGINT, cleanup_processes)
    signal.signal(signal.SIGTERM, cleanup_processes)

    print("[SYSTEM] Initialize Bot Manager...")

    # Start bots one by one
    for bot in BOTS:
        start_bot(bot)

    # Keep main process alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        cleanup_processes(None, None)
