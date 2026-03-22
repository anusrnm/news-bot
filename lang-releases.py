import requests
import logging
from logging.handlers import RotatingFileHandler
import json
import os


# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# Use absolute paths so systemd services always find files in the script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "releases_bot.log")
DATA_FILE = os.path.join(SCRIPT_DIR, "releases_state.json")

# Repositories and their preferred check methods
# 'release' uses /releases/latest; 'tag' uses /tags
REPOS = {
    "Node.js LTS": {"method": "node_lts"},
    "Node.js": {"path": "nodejs/node", "method": "release"},
    "Monaco": {"path": "microsoft/monaco-editor", "method": "release"},
    "Spring Framework": {"path": "spring-projects/spring-framework", "method": "release"},
    "Spring Boot": {"path": "spring-projects/spring-boot", "method": "release"},
    "Bun": {"path": "oven-sh/bun", "method": "release"},
    "Deno": {"path": "denoland/deno", "method": "release"},
    "Rust": {"path": "rust-lang/rust", "method": "release"},
    "Python": {"path": "python/cpython", "method": "tag"},
    "Nim": {"path": "nim-lang/Nim", "method": "tag"},
    "Go": {"path": "golang/go", "method": "go_api"}
}

# 1. Create a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 2. Setup the handler (1MB per file, 3 backups)
# maxBytes = 1 * 1024 * 1024
handler = RotatingFileHandler(LOG_FILE, maxBytes=1024*1024, backupCount=3)
# Add a formatter for readable logs (timestamp, level, message)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    # Switched to HTML mode for better reliability
    payload = {
        "chat_id": CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info("Successfully sent message.")
    except requests.exceptions.HTTPError as e:
        # This will now capture the specific reason for the 400 error
        logger.error(f"Telegram API Error: {e} - Response: {response.text}")
    except Exception as e:
        logger.error(f"Connection error: {e}")

def load_state():
    """Reads the last known versions from a file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    """Saves current versions to a file."""
    with open(DATA_FILE, "w") as f:
        json.dump(state, f)

def get_version(name, config):
    try:
        # Node.js LTS - Filters official index for the latest entry marked as LTS
        if config["method"] == "node_lts":
            res = requests.get("https://nodejs.org/download/release/index.json", timeout=10)
            if res.status_code == 200:
                data = res.json()
                # Find the first entry where 'lts' is not False
                latest_lts = next(v for v in data if v.get('lts') is not False)
                ver = latest_lts['version']
                return ver, f"https://github.com{ver}"
        # Special case for Go official API
        elif config["method"] == "go_api":
            res = requests.get("https://go.dev/dl/?mode=json", timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data[0]["version"], f"https://go.dev{data[0]['version']}"
        
        # Standard GitHub Release
        elif config["method"] == "release":
            res = requests.get(f"https://api.github.com/repos/{config['path']}/releases/latest", timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data.get("tag_name"), data.get("html_url")
        
        # GitHub Tags fallback (for Nim)
        elif config["method"] == "tag":
            res = requests.get(f"https://api.github.com/repos/{config['path']}/tags", timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data:
                    tag_name = data[0]["name"]
                    return tag_name, f"https://github.com/{config['path']}/releases/tag/{tag_name}"
                    
    except Exception as e:
        logger.error(f"Error fetching {name}: {e}")
    return None, None

def main():
    logger.info("Starting fetch...")
    state = load_state()
    
    for name, config in REPOS.items():
        version, url = get_version(name, config)
        if version and state.get(name) != version:
            # Notify only if we already knew about this repo (not first run)
            if name in state:
                msg = f"🚀 *{name} Update!*\nVersion: `{version}`\n[View Details]({url})"
                send_telegram(msg)
            
            state[name] = version
            save_state(state)
            logger.info(f"Updated {name}: {version}")
 

if __name__ == "__main__":
    main()

# Runs every 1 hour
# */60 * * * * /usr/bin/python3 /home/user/workspace/lang-releases.py
