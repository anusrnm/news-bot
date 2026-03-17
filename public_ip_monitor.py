#!/usr/bin/env python3
"""
Public IP Monitor - Alternates between AWS and ipify APIs to check public IP
and sends a Telegram notification when the IP address changes.
"""

import os
import time
import requests
import logging
from datetime import datetime
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration - Set these environment variables or replace with your values
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Check interval in seconds (1 minute = 60 seconds)
CHECK_INTERVAL = 60
# Persist state next to this script so background services always use a stable path.
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ip_state.txt")


class IPMonitor:
    def __init__(self):
        self.previous_ip = self.load_previous_ip()
        self.current_source = 'aws'  # Start with AWS
        
    def load_previous_ip(self) -> Optional[str]:
        """Load the last known IP from file."""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    ip = f.read().strip()
                    if ip:
                        logger.info(f"Loaded previous IP from file: {ip}")
                        return ip
        except Exception as e:
            logger.error(f"Failed to load previous IP: {e}")
        return None
    
    def save_previous_ip(self, ip: str):
        """Save the current IP to file."""
        try:
            with open(DATA_FILE, 'w') as f:
                f.write(ip)
            logger.info(f"Saved IP to file: {ip}")
        except Exception as e:
            logger.error(f"Failed to save IP: {e}")
        
    def get_ip_from_aws(self) -> Optional[str]:
        """Fetch public IP from AWS checkip service."""
        try:
            response = requests.get('https://checkip.amazonaws.com', timeout=5)
            response.raise_for_status()
            ip = response.text.strip()
            logger.info(f"AWS returned IP: {ip}")
            return ip
        except requests.RequestException as e:
            logger.error(f"Failed to get IP from AWS: {e}")
            return None
    
    def get_ip_from_ipify(self) -> Optional[str]:
        """Fetch public IP from ipify API."""
        try:
            response = requests.get('https://api.ipify.org?format=json', timeout=5)
            response.raise_for_status()
            data = response.json()
            ip = data.get('ip')
            if ip:
                logger.info(f"ipify returned IP: {ip}")
            return ip
        except requests.RequestException as e:
            logger.error(f"Failed to get IP from ipify: {e}")
            return None
    
    def get_current_ip(self) -> Optional[str]:
        """Fetch IP using the current source and switch for next time."""
        if self.current_source == 'aws':
            ip = self.get_ip_from_aws()
            self.current_source = 'ipify'
        else:
            ip = self.get_ip_from_ipify()
            self.current_source = 'aws'
        
        return ip
    
    def send_telegram_message(self, message: str) -> bool:
        """Send a message via Telegram."""
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning("Telegram credentials not configured. Message not sent.")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message
            }
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            logger.info("Telegram message sent successfully")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def check_ip(self):
        """Check IP and send notification if changed."""
        logger.info(f"Check using {self.current_source.upper()}")
        source_used = self.current_source.upper()
        
        current_ip = self.get_current_ip()
        
        if current_ip is None:
            logger.warning("Could not retrieve IP address, retrying next cycle")
            return
        
        if self.previous_ip is None:
            # First time - just log it and save
            self.previous_ip = current_ip
            self.save_previous_ip(current_ip)
            logger.info(f"Initial IP recorded: {current_ip}")
        elif current_ip != self.previous_ip:
            # IP changed - send notification and save
            message = (
                f"🔔 Public IP Address Changed\n\n"
                f"Previous IP: {self.previous_ip}\n"
                f"New IP: {current_ip}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Source: {source_used}"
            )
            logger.warning(f"IP changed from {self.previous_ip} to {current_ip}")
            self.send_telegram_message(message)
            self.previous_ip = current_ip
            self.save_previous_ip(current_ip)
        else:
            logger.info(f"IP unchanged: {current_ip}")
    
    def run(self):
        """Main monitoring loop."""
        logger.info("Starting Public IP Monitor")
        logger.info(f"Check interval: {CHECK_INTERVAL} seconds")
        
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning(
                "⚠️  Telegram not configured. Set TELEGRAM_TOKEN and "
                "TELEGRAM_CHAT_ID environment variables"
            )
        
        try:
            while True:
                self.check_ip()
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)


def setup_telegram():
    """Interactive setup for Telegram credentials."""
    print("Telegram Setup")
    print("-" * 40)
    
    token = input("Enter Telegram Bot Token: ").strip()
    chat_id = input("Enter Telegram Chat ID: ").strip()
    
    print("\nSet these environment variables in your shell or .env file:")
    print(f'export TELEGRAM_TOKEN="{token}"')
    print(f'export TELEGRAM_CHAT_ID="{chat_id}"')
    
    print("\nOr create a .env file with these contents:")
    with open('.env.example', 'w') as f:
        f.write(f'TELEGRAM_TOKEN={token}\n')
        f.write(f'TELEGRAM_CHAT_ID={chat_id}\n')
    
    print("Example .env file created as .env.example")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--setup':
        setup_telegram()
    else:
        monitor = IPMonitor()
        monitor.run()
