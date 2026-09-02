"""Persistent ReplyKeyboard панель под полем ввода.

Команды:
  /button  — показать панель (reply к последнему сообщению бота, без пузыря)
  /hidebutton — скрыть панель (пустая reply-панель)
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton, TelegramObject

from src.domain.value_objects.role import UserRole


# FSM-состояния, в которых пользователь вводит данные — панель скрываем
_INPUT_STATES = {
    "waiting_amount", "waiting_month", "waiting_receipt", "waiting_comment",
    "waiting_reason", "waiting_category", "waiting_date",
    "waiting_fee", "waiting_details", "waiting_club_name", "waiting_assessment_day",
    "waiting_telegram_id", "waiting_full_name", "waiting_role",
    "waiting_period", "waiting_adjustment", "waiting_new_name", "waiting_text",
    "ledger_edit_payment_amount", "ledger_edit_payment_month", "ledger_edit_payment_comment",
    "ledger_edit_fine_amount", "ledger_edit_fine_reason", "ledger_edit_fine_comment",
    "ledger_edit_fee_amount", "ledger_edit_fee_month", "ledger_edit_fee_status",
}

# Текст кнопок persistent-панели — навигация, а не ввод данных
_NAV_TEXTS = {
    "💰 Мой бюджет",
    "💼 Бюджет клуба",
    "👑 Управление",
}

# Команда, явно скрывающая панель — middleware не должен мешать
_HIDE_COMMAND = "/hidebutton"


def _is_input_state(state) -> bool:
    if state is None:
        return False
    state_name = state.state if hasattr(state, "state") else str(state)
    if not isinstance(state_name, str):
        return False
    return state_name in _INPUT_STATES or any(s in state_name for s in _INPUT_STATES)


def _is_navigation_event(event: TelegramObject, state) -> bool:
    """Return True if this event is a navigation action, not user input."""
    # Callback navigation
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        if data in ("main_menu", "my_budget", "club_budget", "admin_management",
                     "back", "cancel_action"):
            return True
    # Message-based navigation (persistent panel buttons)
    if isinstance(event, Message) and event.text:
        if event.text.strip() in _NAV_TEXTS:
            return True
        # Explicit hide command
        if event.text.strip().lower() == _HIDE_COMMAND:
            return True
    return False


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


class PersistentMenuMiddleware(BaseMiddleware):
    """PostMiddleware: скрывает панель во время ввода данных.

    Управление панелью — через команды /button и /hidebutton.
    Middleware здесь только предотвращает показ панели при вводе.
    Навигационные события (кнопки меню, /hidebutton) не вызывают скрытие.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Скрываем панель только во время ВВОДА данных, не при навигации
        state = data.get("state")
        if _is_input_state(state) and not _is_navigation_event(event, state):
            # Отправляем пустую панель — скрываем кнопки
            if isinstance(event, (Message, CallbackQuery)):
                user_id: int | None = None
                bot = data.get("bot")
                if isinstance(event, Message):
                    user_id = event.from_user.id if event.from_user else None
                elif isinstance(event, CallbackQuery):
                    user_id = event.from_user.id
                if user_id and bot:
                    empty_kb = ReplyKeyboardMarkup(
                        keyboard=[],
                        resize_keyboard=True,
                        one_time_keyboard=False,
                        is_persistent=True,
                    )
                    chat_id = event.chat.id if isinstance(event, Message) else (event.message.chat.id if event.message else None)
                    if chat_id:
                        try:
                            await bot.send_message(chat_id, "", reply_markup=empty_kb)
                        except Exception:
                            pass
        return await handler(event, data)
