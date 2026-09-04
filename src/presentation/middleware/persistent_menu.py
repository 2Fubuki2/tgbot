"""Persistent ReplyKeyboard панель под полем ввода.

Команды:
  /button  — показать панель (reply к последнему сообщению бота, без пузыря)
  /hidebutton — скрыть панель (пустая reply-панель)

Панель всегда видна, кроме явного /hidebutton.
Восстанавливается после каждого сообщения — Telegram клиент скрывает
панель при фокусе на поле ввода, но она возвращается сразу после обработки.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    TelegramObject,
)

from src.domain.value_objects.role import UserRole

logger = logging.getLogger(__name__)

# Текст команд persistent-панели
_HIDE_COMMAND = "/hidebutton"

# Множество ID чатов, где панель явно скрыта (через /hidebutton)
_hidden_chats: set[int] = set()


def build_reply_keyboard(role: UserRole) -> ReplyKeyboardMarkup:
    """Собрать persistent ReplyKeyboard — кнопки под полем ввода."""
    if role == UserRole.MEMBER:
        role_btns = [("💰 Мой бюджет", "my_budget")]
    elif role == UserRole.TREASURER:
        role_btns = [("💰 Мой бюджет", "my_budget"), ("💼 Бюджет клуба", "club_budget")]
    elif role == UserRole.ADMIN:
        role_btns = [("💰 Мой бюджет", "my_budget"), ("💼 Бюджет клуба", "club_budget"),
                     ("👑 Управление", "admin_management")]
    else:
        role_btns = []

    # Убираем дубликаты по тексту
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for b in role_btns:
        if b[0] not in seen:
            seen.add(b[0])
            deduped.append(b)

    rows: list[list[KeyboardButton]] = []
    for i in range(0, len(deduped), 3):
        chunk = deduped[i:i + 3]
        rows.append([KeyboardButton(text=b[0]) for b in chunk])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def hide_keyboard(chat_id: int) -> None:
    """Пометить чат как скрытый (панель не должна восстанавливаться)."""
    _hidden_chats.add(chat_id)


def show_keyboard(chat_id: int) -> None:
    """Снять блокировку скрытия для чата."""
    _hidden_chats.discard(chat_id)


def is_keyboard_hidden(chat_id: int) -> bool:
    """Проверка, скрыта ли панель для чата."""
    return chat_id in _hidden_chats


class PersistentMenuMiddleware(BaseMiddleware):
    """OuterMiddleware: восстанавливает persistent панель после каждого сообщения.

    Регистрируется на dp.update.outer_middleware(), поэтому оборачивает
    обработку ВСЕХ событий. Для сообщений выполняет post-processing:
    после завершения handler панель отправляется заново, если не скрыта
    командой /hidebutton.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Работаем только с входящими сообщениями
        if not isinstance(event, Message):
            return await handler(event, data)

        chat_id = event.chat.id
        user_id = event.from_user.id if event.from_user else None

        # Команда /hidebutton — скрываем панель и пропускаем handler
        if event.text and event.text.strip().lower() == _HIDE_COMMAND:
            hide_keyboard(chat_id)
            return await handler(event, data)

        # Команда /button — показываем панель, пропускаем handler
        if event.text and event.text.strip().lower() == "/button":
            show_keyboard(chat_id)
            return await handler(event, data)

        # Обычное сообщение: запускаем handler, затем восстанавливаем панель
        was_hidden = is_keyboard_hidden(chat_id)
        result = await handler(event, data)

        # Восстанавливаем панель после handler, если она не скрыта
        if not was_hidden and not is_keyboard_hidden(chat_id):
            await self._restore_keyboard(event, data, user_id=user_id)

        return result

    async def _restore_keyboard(
        self,
        event: Message,
        data: dict[str, Any],
        user_id: int | None = None,
    ) -> None:
        """Отправить persistent панель в чат."""
        bot = data.get("bot")
        if not bot:
            return

        chat_id = event.chat.id
        if is_keyboard_hidden(chat_id):
            return

        # Определяем роль пользователя для кнопок
        role = UserRole.MEMBER  # default
        if user_id is not None:
            try:
                from src.infrastructure.database.session import (
                    get_session,
                )
                from src.infrastructure.repositories.user_repository import (
                    UserRepository,
                )
                async for session in get_session():
                    repo = UserRepository(session)
                    user = await repo.get_by_telegram_id(user_id)
                    if user and user.role in UserRole:
                        role = user.role
                        break
            except Exception:
                logger.warning("Failed to lookup user role for keyboard", exc_info=True)

        kb = build_reply_keyboard(role)
        try:
            await bot.send_message(chat_id, "", reply_markup=kb)
        except Exception:
            logger.warning("Failed to send persistent keyboard", exc_info=True)
