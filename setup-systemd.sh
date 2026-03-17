#!/bin/bash
# Setup script for systemd services on Raspberry Pi
# Run with: sudo bash setup-systemd.sh

set -e

echo "🤖 Setup Telegram News Bot Services"
echo "===================================="
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "❌ This script must be run as root (use: sudo bash setup-systemd.sh)"
    exit 1
fi

# Get installation path
read -p "Enter project path (default: /home/pi/news-bot): " PROJECT_PATH
PROJECT_PATH=${PROJECT_PATH:-/home/pi/news-bot}

if [[ ! -d "$PROJECT_PATH" ]]; then
    echo "❌ Directory does not exist: $PROJECT_PATH"
    exit 1
fi

echo "✓ Using project path: $PROJECT_PATH"
echo ""

# Get Telegram credentials
read -p "Enter Telegram Bot Token: " TELEGRAM_TOKEN
read -p "Enter Telegram Chat ID: " TELEGRAM_CHAT_ID

if [[ -z "$TELEGRAM_TOKEN" || -z "$TELEGRAM_CHAT_ID" ]]; then
    echo "❌ Telegram credentials cannot be empty"
    exit 1
fi

echo ""
echo "📝 Creating environment file..."

# Create environment file
cat > /etc/news-bot.env << EOF
TELEGRAM_TOKEN=$TELEGRAM_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID
EOF

chmod 600 /etc/news-bot.env
echo "✓ Created /etc/news-bot.env (mode 600)"
echo ""

# Create public-ip-monitor service
echo "📝 Creating public-ip-monitor service..."
cat > /etc/systemd/system/public-ip-monitor.service << EOF
[Unit]
Description=Public IP Monitor Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=$PROJECT_PATH
EnvironmentFile=/etc/news-bot.env
ExecStart=/usr/bin/python3 $PROJECT_PATH/public_ip_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Created /etc/systemd/system/public-ip-monitor.service"
echo ""

# Create lang-releases service (runs once per hour)
echo "📝 Creating lang-releases service..."
cat > /etc/systemd/system/lang-releases.service << EOF
[Unit]
Description=Language Releases Tracker Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=$PROJECT_PATH
EnvironmentFile=/etc/news-bot.env
ExecStart=/usr/bin/python3 $PROJECT_PATH/lang-releases.py

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Created /etc/systemd/system/lang-releases.service"
echo ""

# Create lang-releases timer (runs hourly)
echo "📝 Creating lang-releases timer..."
cat > /etc/systemd/system/lang-releases.timer << EOF
[Unit]
Description=Run Language Releases Tracker Hourly

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h

[Install]
WantedBy=timers.target
EOF

echo "✓ Created /etc/systemd/system/lang-releases.timer"
echo ""

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload
echo "✓ Systemd daemon reloaded"
echo ""

# Enable services
echo "🚀 Enabling services..."
systemctl enable public-ip-monitor.service
echo "✓ Enabled public-ip-monitor.service"

systemctl enable lang-releases.timer
echo "✓ Enabled lang-releases.timer"
echo ""

# Start services
echo "▶️  Starting services..."
systemctl start public-ip-monitor.service
echo "✓ Started public-ip-monitor.service"

systemctl start lang-releases.timer
echo "✓ Started lang-releases.timer"
echo ""

# Show status
echo "📊 Service Status:"
echo "=================="
systemctl status public-ip-monitor.service --no-pager
echo ""
systemctl status lang-releases.timer --no-pager
echo ""

# Show next timer trigger
echo "⏱️  Next lang-releases scheduled run:"
systemctl list-timers lang-releases.timer --no-pager
echo ""

echo "✅ Setup Complete!"
echo ""
echo "Useful commands:"
echo "  - Check logs:     sudo journalctl -u public-ip-monitor -f"
echo "  - Check logs:     sudo journalctl -u lang-releases -f"
echo "  - Stop service:   sudo systemctl stop public-ip-monitor"
echo "  - Restart timer:  sudo systemctl restart lang-releases.timer"
echo "  - View all logs:  sudo journalctl -n 50"
