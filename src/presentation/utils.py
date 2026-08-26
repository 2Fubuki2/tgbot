from __future__ import annotations

from typing import cast

from aiogram.types import CallbackQuery, Message

from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.texts import ACCESS_DENIED


async def safe_edit(callback: CallbackQuery, *args, **kwargs) -> None:
    """Safely edit callback message if present, otherwise answer the callback."""
    if callback.message is None:
        await callback.answer()
        return
    msg = cast(Message, callback.message)
    await msg.edit_text(*args, **kwargs)


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
        if user and (user.role == UserRole.TREASURER or user.role == UserRole.ADMIN):
            is_allowed = True
    if not is_allowed:
        await callback.answer("⛔ Нет доступа", show_alert=True)
    return is_allowed
