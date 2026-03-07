import feedparser
import requests
import logging
import json
import html
import os
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RSS_URL = "https://feeds.bbci.co.uk/news/rss.xml"
LOG_FILE = "news_bot.log"
DB_FILE = "feed_history.json"

# Add as many RSS links as you like here
FEEDS = {
    "BBC News": "https://feeds.bbci.co.uk/news/rss.xml",
    "BBC Asia": "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
    "BBC Tech": "https://feeds.bbci.co.uk/news/technology/rss.xml"
}

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    # Switched to HTML mode for better reliability
    payload = {
        "chat_id": CHAT_ID, 
        "text": message, 
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        logging.info("Successfully sent message.")
    except requests.exceptions.HTTPError as e:
        # This will now capture the specific reason for the 400 error
        logging.error(f"Telegram API Error: {e} - Response: {response.text}")
    except Exception as e:
        logging.error(f"Connection error: {e}")

def load_history():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(DB_FILE, "w") as f:
        json.dump(history, f)

def main():
    logging.info("Starting fetch...")
    history = load_history()
    
    for name, url in FEEDS.items():
        feed = feedparser.parse(url)
        if not feed.entries:
            logging.warning(f"No entries found for {url}")
            continue

        # Get last sent link for this feed
        last_sent_link = history.get(name)
        new_items = []

        # Collect all new items since last sent
        for entry in feed.entries:
            if entry.link == last_sent_link:
                break
            new_items.append(entry)


        # Aggregate and send one message per feed
        if new_items:
            msg_lines = [f"<b>[{name}]</b>"]
            for entry in reversed(new_items):
                clean_title = html.escape(entry.title)
                msg_lines.append(f"{clean_title}\n{entry.link}")
            msg = "\n\n".join(msg_lines)
            send_telegram(msg)
            history[name] = new_items[0].link

    save_history(history)

if __name__ == "__main__":
    main()

# Runs every 30 minutes
# */30 * * * * /usr/bin/python3 /home/user/news-bot/app.py
