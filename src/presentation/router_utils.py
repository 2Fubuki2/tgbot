from __future__ import annotations

from decimal import Decimal

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.whitelist_repository import WhitelistRepository


async def register_or_get_user(
    message: Message,
    session: AsyncSession,
    admin_ids: list[int],
) -> User | None:
    """Register user on /start or return existing one.

    If the user already exists, their @username and display name are
    auto-synced from Telegram.
    For new users:
    - If user ID is in admin_ids -> register as ADMIN.
    - If user @username is in Whitelist -> activate account with assigned role.
    - Otherwise (closed club) -> return None (access denied).
    """
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(message.from_user.id)

    if user:
        # Автосинхронизация username и full_name при каждом /start
        new_username = message.from_user.username or ""
        new_full_name = message.from_user.full_name or "Без имени"
        if (user.username or "") != new_username or user.full_name != new_full_name:
            user.username = new_username or user.username
            user.full_name = new_full_name
            try:
                user = await repo.update(user)
            except ValueError:
                pass  # нельзя обновить — оставляем как есть
        return user

    # 1. Проверяем, является ли пользователь администратором из config/env
    is_admin = message.from_user.id in admin_ids
    if is_admin:
        user = User(
            id=None,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name or "Администратор",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            joined_at=message.date,
            phone=None,
            balance_credit=Decimal(0),
        )
        return await repo.create(user)

    # 2. Проверяем наличие в списке приглашений (Whitelist) по @username
    if message.from_user.username:
        wl_repo = WhitelistRepository(session)
        invite = await wl_repo.get_by_username(message.from_user.username)
        if invite and not invite.is_used:
            user = User(
                id=None,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=invite.full_name or message.from_user.full_name or "Без имени",
                role=invite.role,
                status=UserStatus.ACTIVE,
                joined_at=message.date,
                phone=None,
                balance_credit=Decimal(0),
            )
            created_user = await repo.create(user)
            await wl_repo.mark_used(invite.id)
            return created_user

    # 3. Закрытый клуб: пользователь не в вайтлисте и не в admin_ids
    return None

