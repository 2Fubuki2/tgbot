"""PostMiddleware: persistent ReplyKeyboard под полем ввода.

Telegram показывает persistent ReplyKeyboard (кнопки под полем ввода)
только когда бот отправляет сообщение БЕЗ reply_to_message_id.
Middleware отправляет клавиатуру как обычное сообщение через bot.send_message,
а не как ответ через event.answer().
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, cast

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton, TelegramObject

from src.domain.value_objects.role import UserRole
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.middleware.navigation import get_nav_history

logger = logging.getLogger(__name__)

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

# Состояние: chat_id -> последний отправленный экран
_kb_state: Dict[int, str] = {}

# Экраны, на которых показываем persistent-кнопки (верхнеуровневые)
_PERSISTENT_SCREENS = {"main_menu", "my_budget", "club_budget", "admin_management"}


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

    # Кнопки по текущему экрану (пока пусто — все кнопки по роли)
    screen_buttons: dict[str, list[tuple[str, str]]] = {}
    flat_buttons.extend(screen_buttons.get(current, []))

    # Кнопки по роли
    if role == UserRole.MEMBER:
        role_btns = [("💰 Мой бюджет", "my_budget")]
    elif role == UserRole.TREASURER:
        role_btns = [("💰 Мой бюджет", "my_budget"), ("💼 Бюджет клуба", "club_budget")]
    elif role == UserRole.ADMIN:
        role_btns = [("💰 Мой бюджет", "my_budget"), ("💼 Бюджет клуба", "club_budget"),
                     ("👑 Управление", "admin_management")]
    else:
        role_btns = []
    flat_buttons.extend(role_btns)

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
    )


def _get_kb_text(screen: str, nav_history: list[str]) -> str:
    """Текст-подсказка над persistent-кнопками."""
    current = nav_history[-1] if nav_history else "main_menu"
    if current == "main_menu":
        return "👇 Выберите раздел"
    elif current == "my_budget":
        return "💰 Мой бюджет"
    elif current == "club_budget":
        return "💼 Бюджет клуба"
    elif current == "admin_management":
        return "👑 Управление"
    else:
        return "👇 Выберите раздел"


class PersistentMenuMiddleware(BaseMiddleware):
    """PostMiddleware: отправляет persistent ReplyKeyboard как обычное сообщение.

    Отправляет клавиатуру только один раз при входе на верхнеуровневый экран.
    Не спамит при каждом клике по sub-page (member_account, member_payments и т.д.).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        result = await handler(event, data)

        # Скрываем панель во время ввода данных
        state = data.get("state")
        if _is_input_state(state):
            return result

        # Определяем пользователя и чат
        user_id: int | None = None
        chat_id: int | None = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            if event.message:
                chat_id = event.message.chat.id

        if user_id is None or chat_id is None:
            return result

        nav_history = get_nav_history(user_id)
        screen = nav_history[-1] if nav_history else "main_menu"

        # Не показываем persistent-меню на sub-page экранах
        if screen not in _PERSISTENT_SCREENS:
            return result

        # Определяем роль пользователя
        role: UserRole = UserRole.MEMBER
        async for session in get_session():
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(user_id)
            if user:
                role = user.role
                break

        kb = _build_reply_kb(role, nav_history)
        kb_text = _get_kb_text(screen, nav_history)

        # Отправляем клавиатуру если:
        # - это первое сообщение для чата
        # - экран изменился относительно последнего отправленного
        last_screen = _kb_state.get(chat_id)
        if last_screen != screen:
            bot: Bot = cast(Bot, data["bot"])
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=kb_text,
                    reply_markup=kb,
                )
                _kb_state[chat_id] = screen
                logger.info("PersistentMenu: sent kb user=%s chat=%s screen=%s role=%s",
                            user_id, chat_id, screen, role.name)
            except Exception:
                logger.exception("Failed to send persistent menu for user %s", user_id)

        return result
