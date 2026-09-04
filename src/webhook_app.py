"""
Webhook entry point for PythonAnywhere / production.

Flasks receives updates from Telegram via POST /webhook
and feeds them to the aiogram dispatcher.
"""

import asyncio
import logging

from flask import Flask, jsonify, request

from src.config.logger import setup_logging
from src.infrastructure.database.base import Base
from src.infrastructure.database.session import engine
from src.presentation.bot import create_bot, create_dispatcher

setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = create_bot()
dp = create_dispatcher()

# Store the running event loop reference
_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    """Get or create an event loop."""
    global _loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    _loop = loop
    return loop


@app.route("/", methods=["GET"])
def index():
    return "🤖 TreasuryBot is running!", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming Telegram updates."""
    update_data = request.get_json(force=True)
    if not update_data:
        return jsonify({"error": "No data"}), 400

    try:
        asyncio.run(dp.feed_raw_update(bot, update_data))
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True}), 200


@app.route("/set_webhook", methods=["GET", "POST"])
def set_webhook():
    """Set the webhook URL for the bot."""
    host = request.headers.get("Host", "unknown")
    webhook_url = f"https://{host}/webhook"

    try:
        result = asyncio.run(
            bot.set_webhook(url=webhook_url, allowed_updates=["message", "callback_query"])
        )
        status = "✅ Webhook set" if result else "❌ Failed"
        return jsonify({"status": status, "url": webhook_url}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/delete_webhook", methods=["GET"])
def delete_webhook():
    """Delete the webhook."""
    try:
        asyncio.run(bot.delete_webhook())
    except Exception as e:
        logger.error(f"delete_webhook error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "✅ Webhook deleted"}), 200


@app.before_request
def _ensure_tables():
    """Ensure database tables exist before first request."""
    if not hasattr(app, "_db_checked"):
        try:
            asyncio.run(_init_db())
        except Exception as e:
            logger.error(f"DB init error: {e}")
        app._db_checked = True


async def _init_db() -> None:
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")


# For local testing
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
