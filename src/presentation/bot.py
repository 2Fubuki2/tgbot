"""Bot initialization — assembles dispatcher with all routers."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from src.config.settings import settings
from src.presentation.handlers import (
    admin,
    common,
    fines,
    money,
    treasurer,
)

# Import history/member handlers if they exist
try:
    from src.presentation.handlers import member
except ImportError:
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


def create_dispatcher() -> Dispatcher:
    """Create and configure the bot dispatcher with all routers."""
    dp = Dispatcher()

    # Register middleware
    from src.presentation.middleware import NavigationMiddleware
    dp.callback_query.middleware(NavigationMiddleware())

    # Register startup handler
    dp.startup.register(on_startup)

    # Register routers
    dp.include_router(common.router)
    dp.include_router(money.router)
    dp.include_router(fines.router)
    dp.include_router(treasurer.router)
    dp.include_router(admin.router)
    if member:
        dp.include_router(member.router)

    return dp


def create_bot() -> Bot:
    """Create the bot instance."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
