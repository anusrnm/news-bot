# Public IP Telegram Monitor

Monitors your public IP every minute, alternating between AWS and ipify.
When the IP changes, it sends a Telegram message.

## Features

- Checks every 60 seconds
- Alternates sources each run:
  - AWS: `https://checkip.amazonaws.com`
  - ipify: `https://api.ipify.org?format=json`
- Sends Telegram alert only when IP changes
- Persists last known IP in `ip_state.txt`

## Requirements

- Python 3.9+
- Packages in `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Set environment variables:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

Option A: export in shell

```bash
export TELEGRAM_TOKEN="<your-bot-token>"
export TELEGRAM_CHAT_ID="<your-chat-id>"
```

Option B: use `.env` in the project directory

```env
TELEGRAM_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
```

## Run Manually

```bash
python3 public_ip_monitor.py
```

## Run In Background On Raspberry Pi (Recommended)

Use `systemd` for auto-start on boot and crash recovery.

### Automated Setup (Easiest)

Run the setup script on your Raspberry Pi:

```bash
sudo bash setup-systemd.sh
```

This will:
1. Prompt for Telegram credentials
2. Create both service files
3. Create the environment file
4. Enable and start both services
5. Show status and logs

### Manual Setup

Alternatively, follow these steps manually:

#### 1. Copy project to Pi

Example target path:

`/home/pi/news-bot`

#### 2. Create environment file

Create `/etc/news-bot.env`:

```bash
TELEGRAM_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
```

Secure it:

```bash
sudo chmod 600 /etc/news-bot.env
```

#### 3. Create systemd service files

**Public IP Monitor** (`/etc/systemd/system/public-ip-monitor.service`):

```ini
[Unit]
Description=Public IP Monitor Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/news-bot
EnvironmentFile=/etc/news-bot.env
ExecStart=/usr/bin/python3 /home/pi/news-bot/public_ip_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Lang Releases** (`/etc/systemd/system/lang-releases.service`):

```ini
[Unit]
Description=Language Releases Tracker Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/news-bot
EnvironmentFile=/etc/news-bot.env
ExecStart=/usr/bin/python3 /home/pi/news-bot/lang-releases.py

[Install]
WantedBy=multi-user.target
```

**Lang Releases Timer** (`/etc/systemd/system/lang-releases.timer`):

```ini
[Unit]
Description=Run Language Releases Tracker Hourly

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h

[Install]
WantedBy=timers.target
```

#### 4. Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable public-ip-monitor
sudo systemctl enable lang-releases.timer
sudo systemctl start public-ip-monitor
sudo systemctl start lang-releases.timer
```

#### 5. Check status and logs

**IP Monitor:**
```bash
sudo systemctl status public-ip-monitor
sudo journalctl -u public-ip-monitor -f
```

**Releases Tracker:**
```bash
sudo systemctl status lang-releases
sudo journalctl -u lang-releases -f
```

**Timer schedule:**
```bash
sudo systemctl list-timers lang-releases.timer
```

## Notes

- The state file is stored at the script directory path as `ip_state.txt`.
- On first run, the script records current IP and does not send alert.
- Alerts are sent only when a new IP differs from stored IP.
