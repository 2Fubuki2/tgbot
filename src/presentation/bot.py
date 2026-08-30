"""Bot initialization — assembles dispatcher with all routers."""

import importlib
import logging

from aiogram import Bot, Dispatcher, exceptions
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, CallbackQuery, ErrorEvent, Message

from src.config.settings import settings
from src.presentation.handlers import (
    admin,
    common,
    fines,
    ledger_edit,
    money,
    treasurer,
)

logger = logging.getLogger(__name__)


async def error_handler(event: ErrorEvent) -> None:
    """Log unexpected exceptions during event processing."""
    exception = event.exception
    logger.error("Unhandled exception in handler", exc_info=exception)
    update = event.update
    if isinstance(update, CallbackQuery) and not update.answered:
        try:
            await update.answer("⚠️ Произошла ошибка, попробуйте ещё раз.", show_alert=True)
        except exceptions.TelegramRESTRateLimit as e:
            logger.warning("Rate limit on callback answer: %s", e)
        except exceptions.TelegramBadRequest:
            pass
    elif isinstance(update, Message):
        try:
            await update.answer(f"⚠️ Ошибка: {exception}")
        except exceptions.TelegramRESTRateLimit as e:
            logger.warning("Rate limit on message answer: %s", e)

# Import history/member handlers if they exist
try:
    member = importlib.import_module("src.presentation.handlers.member")
except ModuleNotFoundError:
    member = None


async def set_bot_commands(bot: Bot) -> None:
    """Set bot commands in the menu button."""
    commands = [
        BotCommand(command="start", description="🚀 Запустить / главное меню"),
        BotCommand(command="menu", description="📋 Главное меню"),
        BotCommand(command="help", description="❓ Помощь / команды"),
    ]
    await bot.set_my_commands(commands)


async def on_startup(bot: Bot) -> None:
    """Called on bot startup."""
    await set_bot_commands(bot)


# Глобальная переменная для middleware
_bot_status_middleware = None


def create_dispatcher() -> Dispatcher:
    """Create and configure the bot dispatcher with all routers."""
    dp = Dispatcher()

    # Register middleware
    from src.presentation.middleware import NavigationMiddleware, BotStatusMiddleware

    navigation_middleware = NavigationMiddleware()
    bot_status_middleware = BotStatusMiddleware()

    dp.message.middleware(bot_status_middleware)
    dp.callback_query.middleware(bot_status_middleware)
    dp.callback_query.middleware(navigation_middleware)

    # Store middleware globally for access from handlers
    global _bot_status_middleware
    _bot_status_middleware = bot_status_middleware

    # Register error handler
    dp.errors.register(error_handler)

    # Register startup handler
    dp.startup.register(on_startup)

    # Register routers
    dp.include_router(common.router)
    dp.include_router(money.router)
    dp.include_router(fines.router)
    dp.include_router(treasurer.router)
    dp.include_router(admin.router)
    dp.include_router(ledger_edit.router)
    if member:
        dp.include_router(member.router)

    return dp


def get_bot_status_middleware():
    """Get bot status middleware instance."""
    return _bot_status_middleware


def create_bot() -> Bot:
    """Create the bot instance."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
