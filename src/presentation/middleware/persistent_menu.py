"""Middleware для показа.persistent bottom button bar после каждого текстового сообщения."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.domain.value_objects.role import UserRole
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.keyboards.common import persistent_menu_keyboard
from src.presentation.middleware.navigation import get_nav_history

logger = logging.getLogger(__name__)

# FSM-состояния, в которых пользователь вводит данные — кнопка не показываем
_INPUT_STATES = {
    # Payment flow
    "waiting_amount",
    "waiting_month",
    "waiting_receipt",
    "waiting_comment",
    # Fine flow
    "waiting_reason",
    # Expense flow
    "waiting_category",
    "waiting_date",
    # Settings flow
    "waiting_fee",
    "waiting_details",
    "waiting_club_name",
    "waiting_assessment_day",
    # Add user
    "waiting_telegram_id",
    "waiting_full_name",
    "waiting_role",
    # Assess fees
    "waiting_period",
    # Treasury adjust
    "waiting_adjustment",
    # Rename
    "waiting_new_name",
    # Broadcast
    "waiting_text",
    # Ledger edit (raw state names, not class-based)
    "ledger_edit_payment_amount",
    "ledger_edit_payment_month",
    "ledger_edit_payment_comment",
    "ledger_edit_fine_amount",
    "ledger_edit_fine_reason",
    "ledger_edit_fine_comment",
    "ledger_edit_fee_amount",
    "ledger_edit_fee_month",
    "ledger_edit_fee_status",
}


class PersistentMenuMiddleware(BaseMiddleware):
    """После каждого текстового сообщения показывает persistent-панель кнопок
    (если пользователь не в процессе ввода данных)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        msg = event
        if msg.text is None or msg.text.startswith("/"):
            return await handler(event, data)

        # Если пользователь в FSM-состоянии ввода — не показываем панель
        state = data.get("state")
        if state is not None:
            state_name = state.state if hasattr(state, "state") else str(state)
            if state_name in _INPUT_STATES or any(s in state_name for s in _INPUT_STATES):
                return await handler(event, data)

        user_id = msg.from_user.id if msg.from_user else msg.chat.id

        # Получаем роль и историю навигации
        nav_history = get_nav_history(user_id)
        role: UserRole = UserRole.MEMBER  # default

        async for session in get_session():
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(user_id)
            if user:
                role = user.role

        kb = persistent_menu_keyboard(role, nav_history)

        try:
            await msg.answer(
                "💡 <b>Навигация</b>",
                reply_markup=kb,
            )
        except Exception:
            logger.exception("Failed to send persistent menu for user %s", user_id)

        return await handler(event, data)
