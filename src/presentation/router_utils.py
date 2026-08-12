from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.repositories.user_repository import UserRepository


async def register_or_get_user(
    message: Message,
    session: AsyncSession,
    admin_ids: list[int],
) -> User | None:
    """Register user on /start or return existing one."""
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(message.from_user.id)

    if user:
        return user

    # New user registration
    is_admin = message.from_user.id in admin_ids
    role = UserRole.ADMIN if is_admin else UserRole.MEMBER

    user = User(
        id=None,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name or "Без имени",
        role=role,
        status=UserStatus.ACTIVE,
        joined_at=message.date,
        phone=None,
        balance_credit=0,
    )
    user = await repo.create(user)
    return user
