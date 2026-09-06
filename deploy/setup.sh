#!/usr/bin/env bash
# Run this from inside the cloned repo on the VM, e.g.:
#   git clone https://github.com/nabilhrs/social-summary-bot.git
#   cd social-summary-bot
#   bash deploy/setup.sh
set -euo pipefail

echo "==> Installing system dependencies..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git build-essential

echo "==> Creating virtual environment..."
python3 -m venv venv

echo "==> Installing Python dependencies (yt-dlp's extras pull in a few extra packages, may take a minute)..."
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
    echo "==> Creating .env from .env.example — you must edit it before starting the bot."
    cp .env.example .env
else
    echo "==> .env already exists, leaving it as-is."
fi

echo
echo "Setup complete. Next steps:"
echo "  1. Edit .env with your real values:"
echo "       nano .env"
echo "     (TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_IDS, GEMINI_API_KEY)"
echo "  2. Install the systemd service so the bot runs continuously and restarts on crash/reboot:"
echo "       sudo cp deploy/social-summary-bot.service /etc/systemd/system/"
echo "       sudo systemctl daemon-reload"
echo "       sudo systemctl enable --now social-summary-bot"
echo "  3. Watch it start up:"
echo "       journalctl -u social-summary-bot -f"
