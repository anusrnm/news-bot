#!/usr/bin/env python3
"""
Camera Bot - Captures an image from the Raspberry Pi camera and sends it
back via Telegram whenever a user sends a message to the bot.

Supported camera stacks (tried in order):
    1. rpicam-still     — Raspberry Pi OS Bookworm (recommended)
    2. libcamera-still  — Raspberry Pi OS Bullseye
    3. raspistill       — legacy camera stack (older Raspbian / legacy mode)

Setup:
    1. Export TELEGRAM_TOKEN and optional TELEGRAM_CHAT_ID in the shell,
         or use a systemd EnvironmentFile.
    2. Enable the camera with `sudo raspi-config` -> Interface Options -> Camera.
    3. pip install -r requirements.txt
    4. python3 camera_bot.py
"""

import io
import logging
import os
import subprocess
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
# Comma-separated list of chat IDs that are allowed to use the bot.
# Leave empty to allow everyone (not recommended for a camera bot).
_raw_ids = os.getenv("TELEGRAM_CHAT_ID", "")
ALLOWED_CHAT_IDS: set[str] = {cid.strip() for cid in _raw_ids.split(",") if cid.strip()}

# Camera capture timeout in seconds
CAPTURE_TIMEOUT = 20

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def _run_capture(cmd: list[str], output_path: str) -> bool:
    """Run a capture command and return True on success."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CAPTURE_TIMEOUT,
        )
        if result.returncode != 0:
            logger.warning(
                "Camera command failed: %s (exit=%s, stderr=%s)",
                cmd[0],
                result.returncode,
                (result.stderr or "").strip(),
            )
        return result.returncode == 0 and os.path.isfile(output_path)
    except FileNotFoundError:
        logger.info("Camera command not found: %s", cmd[0])
        return False  # command not available
    except subprocess.TimeoutExpired:
        logger.warning("Camera command timed out: %s", cmd[0])
        return False


def capture_image() -> bytes:
    """
    Capture a JPEG from the Pi camera and return the raw bytes.

    Tries rpicam-still first (Bookworm), then libcamera-still (Bullseye),
    then falls back to raspistill (legacy stack) to support the widest
    range of Raspberry Pi OS versions on the RPi 1 B+.

    Raises RuntimeError if neither tool succeeds.
    """
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        output_path = tmp.name

    try:
        # rpicam-still (Bookworm and newer)
        if _run_capture(
            ["rpicam-still", "--output", output_path, "--nopreview",
             "--timeout", "2000"],
            output_path,
        ):
            logger.info("Captured with rpicam-still")
            with open(output_path, "rb") as f:
                return f.read()

        # libcamera-still (Bullseye)
        if _run_capture(
            ["libcamera-still", "--output", output_path, "--nopreview",
             "--timeout", "2000"],
            output_path,
        ):
            logger.info("Captured with libcamera-still")
            with open(output_path, "rb") as f:
                return f.read()

        # raspistill (legacy camera stack - enable via raspi-config or
        # add `start_x=1, gpu_mem=128` to /boot/config.txt)
        if _run_capture(
            ["raspistill", "--output", output_path, "--nopreview",
             "--timeout", "2000"],
            output_path,
        ):
            logger.info("Captured with raspistill")
            with open(output_path, "rb") as f:
                return f.read()

        raise RuntimeError(
            "All camera commands failed (rpicam-still, libcamera-still, raspistill). "
            "Check that the camera module is connected and enabled "
            "(sudo raspi-config → Interface Options → Camera)."
        )
    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


# ---------------------------------------------------------------------------
# Authorization helper
# ---------------------------------------------------------------------------

def is_authorized(update: Update) -> bool:
    """Return True if the sender is in the allowed-chat-IDs list (or the
    list is empty, which disables the restriction)."""
    if not ALLOWED_CHAT_IDS:
        return True
    return str(update.effective_chat.id) in ALLOWED_CHAT_IDS


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with a brief usage description."""
    await update.message.reply_text(
        "Camera Bot ready.\n\n"
        "Send any message or /photo to capture an image from the Pi camera."
    )


async def send_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture a photo and send it back to the requester."""
    if not is_authorized(update):
        logger.warning(
            "Rejected request from unauthorized chat_id=%s",
            update.effective_chat.id,
        )
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    await update.message.reply_text("Capturing image, please wait...")

    try:
        image_bytes = capture_image()
    except RuntimeError as exc:
        logger.error("Capture failed: %s", exc)
        await update.message.reply_text(f"Camera error: {exc}")
        return
    except Exception as exc:
        logger.exception("Unexpected error during capture")
        await update.message.reply_text("An unexpected error occurred. Check the logs.")
        return

    await update.message.reply_photo(
        photo=io.BytesIO(image_bytes),
        caption="Captured from Pi camera",
    )
    logger.info("Photo sent to chat_id=%s", update.effective_chat.id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN is not set. "
            "Export TELEGRAM_TOKEN in the shell or provide it through systemd."
        )

    app = Application.builder().token(TOKEN).build()

    # /start - welcome
    app.add_handler(CommandHandler("start", cmd_start))
    # /photo or /capture - explicit capture command
    app.add_handler(CommandHandler(["photo", "capture"], send_photo))
    # Any text message also triggers a capture
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_photo))

    logger.info("Camera bot started. Waiting for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
