#!/bin/bash
# Setup script for the camera bot systemd service on Raspberry Pi
# Run with: sudo bash setup-camera-bot-service.sh

set -e

echo "Setup Camera Bot Service"
echo "========================"
echo ""

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Use: sudo bash setup-camera-bot-service.sh"
    exit 1
fi

read -r -p "Enter project path (default: /home/pi/news-bot): " PROJECT_PATH
PROJECT_PATH=${PROJECT_PATH:-/home/pi/news-bot}

if [[ ! -d "$PROJECT_PATH" ]]; then
    echo "Directory does not exist: $PROJECT_PATH"
    exit 1
fi

read -r -p "Enter service user (default: pi): " SERVICE_USER
SERVICE_USER=${SERVICE_USER:-pi}

read -r -p "Enter Python path (default: /usr/bin/python3): " PYTHON_BIN
PYTHON_BIN=${PYTHON_BIN:-/usr/bin/python3}

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python executable not found: $PYTHON_BIN"
    exit 1
fi

read -r -p "Enter Telegram Bot Token: " TELEGRAM_TOKEN
read -r -p "Enter allowed Telegram User ID(s), comma-separated: " TELEGRAM_ALLOWED_USER_IDS
read -r -p "Enter allowed Telegram Chat ID(s), comma-separated (optional): " TELEGRAM_CHAT_ID

if [[ -z "$TELEGRAM_TOKEN" ]]; then
    echo "Telegram token cannot be empty"
    exit 1
fi

if [[ -z "$TELEGRAM_ALLOWED_USER_IDS" ]]; then
    echo "At least one allowed Telegram user ID is required"
    exit 1
fi

ENV_FILE=/etc/camera-bot.env
SERVICE_FILE=/etc/systemd/system/camera-bot.service

echo ""
echo "Creating environment file at $ENV_FILE"

cat > "$ENV_FILE" << EOF
TELEGRAM_TOKEN=$TELEGRAM_TOKEN
TELEGRAM_ALLOWED_USER_IDS=$TELEGRAM_ALLOWED_USER_IDS
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID
EOF

chmod 600 "$ENV_FILE"

echo "Creating service file at $SERVICE_FILE"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Telegram Camera Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_PATH
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN $PROJECT_PATH/camera_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd daemon"
systemctl daemon-reload

echo "Enabling camera-bot.service"
systemctl enable camera-bot.service

echo "Starting camera-bot.service"
systemctl restart camera-bot.service

echo ""
echo "Service status:"
systemctl status camera-bot.service --no-pager
echo ""
echo "Useful commands:"
echo "  sudo journalctl -u camera-bot -f"
echo "  sudo systemctl restart camera-bot"
echo "  sudo systemctl stop camera-bot"
echo "  sudo systemctl disable camera-bot"