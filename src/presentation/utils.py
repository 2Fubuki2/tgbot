from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from aiogram.types import CallbackQuery, Message

from src.domain.value_objects.fee_status import FeeStatus
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.texts import ACCESS_DENIED

# Хранилище ID последнего бот-сообщения на чат: chat_id -> message_id
_last_bot_msg_ids: dict[int, int] = {}


def record_bot_message(chat_id: int, message_id: int) -> None:
    """Запомнить ID сообщения, отправленного ботом в чат.
    Используется PersistentMenuMiddleware для reply-отправки клавиатуры."""
    _last_bot_msg_ids[chat_id] = message_id


def get_last_bot_message_id(chat_id: int) -> int | None:
    """Возвращает ID последнего бот-сообщения в чате (если есть)."""
    return _last_bot_msg_ids.get(chat_id)

if TYPE_CHECKING:
    from src.domain.entities.fine import Fine
    from src.domain.entities.monthly_fee import MonthlyFee
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── Status helpers (shared across handlers) ───────────────────

def payment_status_ru(status: PaymentStatus) -> str:
    return {
        PaymentStatus.PENDING: "ожидает",
        PaymentStatus.CONFIRMED: "подтверждён",
        PaymentStatus.REJECTED: "отклонён",
    }.get(status, status.value)


def fee_status_ru(status: FeeStatus) -> str:
    return {
        FeeStatus.PENDING: "ожидает",
        FeeStatus.PAID: "оплачен",
        FeeStatus.WAIVED: "списан",
    }.get(status, status.value)


def fine_status_ru(status: FineStatus) -> str:
    return {
        FineStatus.ACTIVE: "активен",
        FineStatus.CANCELLED: "оплачен",
    }.get(status, status.value)


# ─── Overdue helper ─────────────────────────────────────────────

async def compute_overdue(
    session: AsyncSession, threshold_days: int = 15,
) -> tuple[list[tuple["MonthlyFee", int]], list[tuple["Fine", int]]]:
    """Return (overdue_fees, overdue_fines) where each item is (entity, days_overdue)."""
    from datetime import date as date_cls
    from src.infrastructure.repositories.fee_repository import FeeRepository
    from src.infrastructure.repositories.fine_repository import FineRepository
    from .timezone import today_msk

    today = today_msk()
    fee_repo = FeeRepository(session)
    fine_repo = FineRepository(session)

    overdue_fees: list[tuple["MonthlyFee", int]] = []
    for fee in await fee_repo.list_all_pending():
        if fee.remaining_amount <= 0:
            continue
        assessed = fee.assessed_at
        if assessed.tzinfo is None:
            assessed = assessed.replace(tzinfo=today.tzinfo if hasattr(today, 'tzinfo') else None)
        days = (today - assessed.date()).days
        if days >= threshold_days:
            overdue_fees.append((fee, days))

    overdue_fines: list[tuple["Fine", int]] = []
    for fine in await fine_repo.list_active():
        if fine.remaining_amount <= 0:
            continue
        issued = fine.created_at
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=today.tzinfo if hasattr(today, 'tzinfo') else None)
        days = (today - issued.date()).days
        if days >= threshold_days:
            overdue_fines.append((fine, days))

    return overdue_fees, overdue_fines


async def safe_edit(callback: CallbackQuery, *args, **kwargs) -> None:
    """Safely edit callback message if present, otherwise answer the callback.

    Handles both plain text messages and media messages (photo/video/document):
    media messages are edited via edit_caption instead of edit_text.
    """
    if callback.message is None:
        await callback.answer()
        return
    msg = cast(Message, callback.message)

    # Detect if message has media (photo, video, document, etc.)
    is_media = bool(
        msg.photo
        or msg.video
        or msg.document
        or msg.audio
        or msg.animation
        or msg.voice
        or msg.video_note
        or msg.sticker
    )

    # Extract text/caption from args/kwargs for fallback
    text = kwargs.pop("text", None)
    if text is None and args:
        text = args[0]
        args = args[1:]

    async def fallback_send(text_to_send: str) -> None:
        if callback.bot and callback.message:
            try:
                await callback.bot.send_message(
                    callback.from_user.id,
                    text_to_send,
                    reply_markup=kwargs.get("reply_markup"),
                )
            except Exception:
                logger.exception("safe_edit fallback failed")

    if is_media:
        # For media messages, edit caption
        if kwargs.get("caption") is None:
            kwargs["caption"] = text
        try:
            await msg.edit_caption(**kwargs)
            record_bot_message(msg.chat.id, msg.message_id)
        except Exception:
            logger.exception("safe_edit: failed to edit caption, fallback to send_message")
            await fallback_send(text or "")
    else:
        try:
            await msg.edit_text(text, *args, **kwargs)
            record_bot_message(msg.chat.id, msg.message_id)
        except Exception:
            logger.exception("safe_edit: failed to edit text, fallback to send_message")
            await fallback_send(text or "")


async def send_text_replacing_photo(callback: CallbackQuery, text: str, **kwargs) -> None:
    """Send a text message, deleting the current photo message first if present."""
    msg = callback.message
    if msg and msg.photo:
        try:
            await msg.delete()
        except Exception:
            logger.exception("Failed to delete photo message before sending text")
        await callback.bot.send_message(callback.from_user.id, text, **kwargs)
    else:
        await safe_edit(callback, text, **kwargs)


async def require_role(callback: CallbackQuery, role: UserRole) -> bool:
    """Check if user has required role. Returns True if allowed."""
    is_allowed = False
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)
        if user and user.status == UserStatus.ACTIVE and (user.role == role or user.role == UserRole.ADMIN):
            is_allowed = True
            break
    if not is_allowed:
        await callback.answer(ACCESS_DENIED, show_alert=True)
    return is_allowed


async def require_treasurer_or_admin(callback: CallbackQuery) -> bool:
    """Check if user has treasurer or admin role."""
    is_allowed = False
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)
        if user and user.status == UserStatus.ACTIVE and (user.role == UserRole.TREASURER or user.role == UserRole.ADMIN):
            is_allowed = True
            break
    if not is_allowed:
        await callback.answer(ACCESS_DENIED, show_alert=True)
    return is_allowed


class FakeCallback:
    """Minimal mock of aiogram CallbackQuery for use in message-based flows."""

    def __init__(self, message: Message):
        self.message = message
        self.from_user = message.from_user
        self.bot = message.bot

    async def answer(self) -> None:
        pass
