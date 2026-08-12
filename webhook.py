"""
Webhook entry point для PythonAnywhere.

Используется для запуска бота через webhook вместо polling.
"""

import asyncio
import logging

from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from src.config.logger import setup_logging
from src.config.settings import settings
from src.infrastructure.database.base import Base
from src.infrastructure.database.session import engine
from src.main import _ensure_missing_columns
from src.presentation.bot import create_bot, create_dispatcher

logger = logging.getLogger(__name__)

# Webhook settings
WEBHOOK_PATH = f"/bot/{settings.bot_token}"
WEBHOOK_URL = f"{settings.webhook_domain}{WEBHOOK_PATH}"

# PythonAnywhere web app URL (замените на свой домен)
# Пример: https://yourusername.pythonanywhere.com
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8000


async def on_startup_webhook(app: web.Application) -> None:
    """Действия при запуске webhook."""
    logger.info("Starting webhook setup...")

    # Создание таблиц БД
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_missing_columns)
    logger.info("Database tables created successfully.")

    # Установка webhook
    bot = app["bot"]
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message", "callback_query"])
    logger.info(f"Webhook set to: {WEBHOOK_URL}")


async def on_shutdown_webhook(app: web.Application) -> None:
    """Действия при остановке webhook."""
    bot = app["bot"]
    await bot.delete_webhook()
    await bot.session.close()
    await engine.dispose()
    logger.info("Webhook shutdown complete.")


def main() -> None:
    """Запуск бота в режиме webhook."""
    setup_logging()
    logger.info("Starting TreasuryBot in webhook mode...")

    # Создание бота и диспетчера
    bot = create_bot()
    dp = create_dispatcher()

    # Настройка aiohttp приложения
    app = web.Application()
    app["bot"] = bot

    # Регистрация обработчиков startup/shutdown
    app.on_startup.append(on_startup_webhook)
    app.on_shutdown.append(on_shutdown_webhook)

    # Настройка webhook handler
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Запуск веб-сервера
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)


if __name__ == "__main__":
    main()
