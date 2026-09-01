"""PostMiddleware: injects persistent ReplyKeyboard into bot responses.

Подход: middleware перехватывает ответ бота и добавляет reply_markup,
чтобы кнопки отображались под полем ввода пользователя.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton, TelegramObject

from src.domain.value_objects.role import UserRole
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.middleware.navigation import get_nav_history

logger = logging.getLogger(__name__)

# FSM-состояния, в которых пользователь вводит данные — панель скрываем
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
    # Ledger edit
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


def _is_input_state(state) -> bool:
    if state is None:
        return False
    state_name = state.state if hasattr(state, "state") else str(state)
    if not isinstance(state_name, str):
        return False
    return state_name in _INPUT_STATES or any(s in state_name for s in _INPUT_STATES)


def _build_reply_kb(role: UserRole, nav_history: list[str]) -> ReplyKeyboardMarkup:
    """Собрать persistent ReplyKeyboard — кнопки под полем ввода."""
    current = nav_history[-1] if nav_history else "main_menu"

    flat_buttons: list[tuple[str, str]] = []

    # Кнопки по текущему экрану
    screen_buttons: dict[str, list[tuple[str, str]]] = {
        "main_menu": [],
        "my_budget": [("🏠 Меню", "main_menu")],
        "member_account": [("💰 Платежи", "member_payments"), ("⚠️ Штрафы", "member_fines")],
        "member_payments": [("📋 Лицевой счёт", "member_account")],
        "member_fines": [("💰 Платежи", "member_payments")],
        "member_details": [],
        "club_budget": [("🏠 Меню", "main_menu")],
        "treasurer_pending": [("📋 Участники", "treasurer_members")],
        "treasurer_members": [("⏳ Платежи", "treasurer_pending")],
        "treasurer_fines": [("💸 Расходы", "treasurer_expenses")],
        "treasurer_expenses": [("📋 Участники", "treasurer_members")],
        "treasurer_timeline": [],
        "admin_management": [],
    }
    flat_buttons.extend(screen_buttons.get(current, []))

    # Кнопки по роли
    role_btns: list[tuple[str, str]] = []
    if role == UserRole.MEMBER:
        role_btns = [("💰 Мой бюджет", "my_budget")]
    elif role == UserRole.TREASURER:
        role_btns = [("🏠 Меню", "main_menu"), ("💰 Мой бюджет", "my_budget")]
    elif role == UserRole.ADMIN:
        role_btns = [("🏠 Меню", "main_menu"), ("💰 Мой бюджет", "my_budget"),
                       ("💼 Бюджет клуба", "club_budget")]
    flat_buttons.extend(role_btns)

    # Кнопка «Назад»
    if len(nav_history) > 1 and current != "main_menu":
        flat_buttons.append(("⬅️ Назад", "back"))

    # Убираем дубликаты по тексту
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for b in flat_buttons:
        if b[0] not in seen:
            seen.add(b[0])
            deduped.append(b)
    flat_buttons = deduped

    # Не более 3 кнопок в ряд
    rows: list[list[KeyboardButton]] = []
    for i in range(0, len(flat_buttons), 3):
        chunk = flat_buttons[i:i + 3]
        rows.append([KeyboardButton(text=b[0]) for b in chunk])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="Введите сообщение…",
    )


class PersistentMenuMiddleware(BaseMiddleware):
    """PostMiddleware: injects persistent ReplyKeyboard into bot responses.

    Алгоритм:
    1. Запускает handler
    2. Проверяет FSM — если ввод данных, выходим
    3. Собирает reply-клавиатуру
    4. Отправляет reply_markup как ответ на сообщение пользователя
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        result = await handler(event, data)

        state = data.get("state")
        if _is_input_state(state):
            return result

        user_id: int | None = None
        if isinstance(event, Message):
            if event.text and event.text.startswith("/"):
                return result
            user_id = event.from_user.id if event.from_user else event.chat.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id

        if user_id is None:
            return result

        nav_history = get_nav_history(user_id)

        role: UserRole = UserRole.MEMBER
        async for session in get_session():
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(user_id)
            if user:
                role = user.role
                break

        kb = _build_reply_kb(role, nav_history)

        try:
            if isinstance(event, Message):
                # Отправляем reply_markup как ответ на сообщение пользователя
                await event.answer(reply_markup=kb)
            elif isinstance(event, CallbackQuery) and event.message:
                # Для callback — редактируем сообщение бота, добавляя reply_markup
                try:
                    await event.message.edit_reply_markup(reply_markup=kb)
                except Exception:
                    await event.answer(reply_markup=kb)
        except Exception:
            logger.exception("Failed to inject persistent menu for user %s", user_id)

        return result
