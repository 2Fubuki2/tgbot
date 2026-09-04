"""Middleware для проверки статуса бота (включен/выключен)."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class BotStatusMiddleware(BaseMiddleware):
    """Middleware для проверки, включен ли бот."""

    def __init__(self):
        super().__init__()
        self.bot_running = True  # Глобальный статус бота

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Проверяет, активен ли бот перед обработкой события."""

        # Исключения - команды управления ботом
        if isinstance(event, Message) and event.text:
            text = event.text.strip()
            if text in ["/stop_bot", "/restart_bot", "/start"]:
                return await handler(event, data)

        # Проверяем статус бота
        if not self.bot_running:
            if isinstance(event, Message):
                await event.reply(
                    "⏸️ <b>Бот временно остановлен</b>\n\n"
                    "Администратор остановил бота для обслуживания.\n\n"
                    "Попробуйте позже или свяжитесь с администратором.\n\n"
                    "Для запуска бота используйте команду /start"
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("⏸️ Бот остановлен для обслуживания", show_alert=True)
            return  # Не пропускаем дальше

        # Бот работает - пропускаем
        return await handler(event, data)

    def stop_bot(self) -> None:
        """Остановить бота."""
        self.bot_running = False

    def start_bot(self) -> None:
        """Запустить бота."""
        self.bot_running = True

    def is_running(self) -> bool:
        """Проверить статус бота."""
        return self.bot_running