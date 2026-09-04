"""Глобальное хранилище навигации и middleware."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

# Хранилище навигации: user_id -> список экранов
_nav_stack: dict[int, list[str]] = {}


def get_nav_history(user_id: int) -> list[str]:
    return _nav_stack.get(user_id, ["main_menu"])


def push_nav(user_id: int, screen: str) -> None:
    if user_id not in _nav_stack:
        _nav_stack[user_id] = ["main_menu"]
    history = _nav_stack[user_id]
    if history and history[-1] == screen:
        return
    history.append(screen)
    if len(history) > 10:
        _nav_stack[user_id] = [history[0]] + history[-9:]


def pop_nav(user_id: int) -> str:
    history = _nav_stack.get(user_id, ["main_menu"])
    if len(history) > 1:
        history.pop()
        previous = history[-1]
    else:
        previous = "main_menu"
    return previous


class NavigationMiddleware(BaseMiddleware):
    """Middleware для отслеживания истории навигации пользователя."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        callback_data = event.data or ""
        user_id = event.from_user.id

        if callback_data == "main_menu":
            _nav_stack[user_id] = ["main_menu"]
        elif callback_data == "back":
            pass  # обработается в хендлере
        elif not callback_data.startswith(("confirm_", "cancel_", "skip_", "pay_", "fine_", "back:")):
            push_nav(user_id, callback_data)

        return await handler(event, data)
