"""Middleware для проверки прав доступа и блокировки исключённых пользователей."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, TelegramObject

from src.config.settings import settings
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserAccessMiddleware(BaseMiddleware):
    """Проверяет статус пользователя перед обработкой события.

    1. Администраторы из settings.admin_ids имеют постоянный доступ.
    2. Команда /start всегда пропускается к cmd_start (для первичного онбординга,
       активации по вайтлисту или отображения экрана закрытого клуба).
    3. Если пользователь имеет статус EXPELLED (или любой другой, отличный от ACTIVE) —
       блокирует выполнение любого обработчика, выводит уведомление о блокировке
       и убирает persistent-клавиатуру (ReplyKeyboardRemove).
    4. Если пользователя нет в базе (неавторизованный гость закрытого клуба) —
       блокирует нажатия инлайн-кнопок или текстовых команд и предлагает /start.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user")
        if not from_user:
            return await handler(event, data)

        telegram_id = from_user.id

        # 1. Администраторы из config/env всегда имеют доступ
        if telegram_id in settings.admin_ids:
            return await handler(event, data)

        # 2. Команда /start должна проходить к cmd_start для онбординга и проверки вайтлиста
        if isinstance(event, Message) and event.text:
            text = event.text.strip().lower()
            if text.startswith("/start"):
                return await handler(event, data)

        # 3. Проверяем статус пользователя в базе данных
        user = None
        try:
            async for session in get_session():
                repo = UserRepository(session)
                user = await repo.get_by_telegram_id(telegram_id)
                break
        except Exception:
            logger.exception("Error checking user access in UserAccessMiddleware")
            return await handler(event, data)

        # 4. Пользователь не зарегистрирован в базе данных
        if not user:
            if isinstance(event, Message):
                await event.answer(
                    "🔒 <b>Доступ ограничен</b>\n\n"
                    "Этот бот доступен только авторизованным участникам клуба.\n"
                    "Для авторизации отправьте команду /start",
                    reply_markup=ReplyKeyboardRemove(),
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("🔒 Доступ ограничен. Отправьте /start", show_alert=True)
            return

        # 5. Пользователь исключён или заблокирован
        if user.status != UserStatus.ACTIVE:
            if isinstance(event, Message):
                await event.answer(
                    "❌ <b>Доступ заблокирован</b>\n\n"
                    "Ваш доступ к боту заблокирован администратором.\n"
                    "Если вы считаете, что произошла ошибка, обратитесь к руководству клуба.",
                    reply_markup=ReplyKeyboardRemove(),
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "❌ Ваш доступ к боту заблокирован администратором.",
                    show_alert=True,
                )
            return

        # 6. Пользователь активен — передаём управление дальше
        return await handler(event, data)
