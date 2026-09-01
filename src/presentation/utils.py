from __future__ import annotations

import logging
from typing import cast

from aiogram.types import CallbackQuery, Message

from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.texts import ACCESS_DENIED


logger = logging.getLogger(__name__)


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
        except Exception:
            logger.exception("safe_edit: failed to edit caption, fallback to send_message")
            await fallback_send(text or "")
    else:
        try:
            await msg.edit_text(text, *args, **kwargs)
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
    if not is_allowed:
        await callback.answer("⛔ Нет доступа", show_alert=True)
    return is_allowed
