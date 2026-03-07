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


# def main():
#     logging.info("Starting fetch...")
#     # feedparser handles the schema mapping automatically
#     feed = feedparser.parse(RSS_URL)
    
#     if not feed.entries:
#         logging.warning("No entries found. Check if the URL is blocked or down.")
#         return

#     for entry in feed.entries[:3]:
#         # Escape HTML characters (<, >, &) to prevent 400 errors
#         clean_title = html.escape(entry.title)
#         formatted_msg = f"<b>{clean_title}</b>\n\n{entry.link}"
#         send_telegram(formatted_msg)


def main():
    logging.info("Starting fetch...")
    history = load_history()
    
    for name, url in FEEDS.items():
        feed = feedparser.parse(url)
        if not feed.entries:
            logging.warning(f"No entries found for {url}")
            continue
            
        latest_item = feed.entries[0]
        latest_link = latest_item.link
        
        # Only send if the link is different from the last time we checked THIS feed
        if history.get(name) != latest_link:
            clean_title = html.escape(latest_item.title)
            msg = f"<b>[{name}]</b>\n{clean_title}\n\n{latest_link}"
            
            send_telegram(msg)
            history[name] = latest_link # Update history for this feed

    save_history(history)

if __name__ == "__main__":
    main()

# Runs every 30 minutes
# */30 * * * * /usr/bin/python3 /home/user/news-bot/app.py
