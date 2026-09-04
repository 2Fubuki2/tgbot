"""Bot initialization — assembles dispatcher with all routers."""

import importlib
import logging
from functools import partial as _partial

from aiogram import Bot, Dispatcher, exceptions
from aiogram.client.default import DefaultBotProperties

# Monkey-patch FilterObject.call to workaround Python 3.13 TypeError
from aiogram.dispatcher.event.handler import FilterObject
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, CallbackQuery, ErrorEvent, Message

_original_filter_call = FilterObject.call

async def _patched_filter_call(self, *args, **kwargs):
    callback = self.callback

    # Workaround for Python 3.13: wrap non-callable callbacks
    if not callable(callback):
        if hasattr(callback, "__func__"):
            callback = callback.__func__
        elif callable(callback):
            callback = callback.__call__
        else:
            original_callback = callback
            async def _wrapper(*a, **k):
                try:
                    return await original_callback(*a, **k)
                except Exception as e:
                    raise RuntimeError(f"Non-callable callback wrapper failed: {e}") from e
            callback = _wrapper

    try:
        wrapped = _partial(callback, *args, **self._prepare_kwargs(kwargs))
    except TypeError as e:
        raise TypeError(f"Cannot create partial for callback {callback!r}: {e}") from e

    if self.awaitable:
        return await wrapped()
    import asyncio
    return await asyncio.to_thread(wrapped)

FilterObject.call = _patched_filter_call

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
    from src.presentation.middleware import (
        BotStatusMiddleware,
        NavigationMiddleware,
        PersistentMenuMiddleware,
        UserAccessMiddleware,
    )

    persistent_menu_middleware = PersistentMenuMiddleware()
    navigation_middleware = NavigationMiddleware()
    bot_status_middleware = BotStatusMiddleware()
    user_access_middleware = UserAccessMiddleware()

    # Bot status — проверяет, включен ли бот глобально
    dp.message.middleware(bot_status_middleware)
    dp.callback_query.middleware(bot_status_middleware)

    # User access — проверяет права и блокирует исключённых пользователей
    dp.message.middleware(user_access_middleware)
    dp.callback_query.middleware(user_access_middleware)

    # Navigation — отслеживание истории экранов
    dp.message.middleware(navigation_middleware)
    dp.callback_query.middleware(navigation_middleware)

    # Persistent menu — outer middleware: оборачивает ВСЕ события,
    # выполняет post-processing (восстановление панели) после handler'а
    dp.update.outer_middleware(persistent_menu_middleware)

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
    """Create the bot instance with optional proxy support."""
    session = None
    if settings.proxy_url:
        from aiogram.client.session.aiohttp import AiohttpSession

        session = AiohttpSession(proxy=settings.proxy_url)

    return Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

