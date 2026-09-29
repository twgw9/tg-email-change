#!/usr/bin/env bash
# ==============================================================================
# Alwaysdata 24/7 Deployment & Background Daemon Script
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

# 1. Load .env file if present
if [ -f .env ]; then
    echo "[+] Loading environment from .env file..."
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# 2. Identify Python binary
if [ -d "venv" ] && [ -x "venv/bin/python" ]; then
    PY="venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
else
    echo "[-] Error: Python3 not found in PATH." >&2
    exit 1
fi

echo "[+] Using Python: $PY"

# 3. Ensure dependencies are installed
"$PY" -m pip install -q -r requirements.txt || true

# 4. Supervised Execution Loop (Self-Healing Daemon)
# If the bot process ever terminates unexpectedly, it logs the event and auto-restarts.
echo "[+] Starting 24/7 Supervised Telegram Automation Bot..."
echo "[+] Press Ctrl+C or kill PID to stop."

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting bot instance..."
    "$PY" bot.py || true
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot stopped with exit code $EXIT_CODE."
    
    # If terminated gracefully with code 0 or 130 (SIGINT), exit the loop
    if [ "$EXIT_CODE" -eq 0 ] || [ "$EXIT_CODE" -eq 130 ]; then
        echo "[+] Clean shutdown requested. Exiting."
        break
    fi
    
    echo "[!] Bot crashed or restarted by server. Cooling down 5 seconds before restart..."
    sleep 5
done
