from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.whitelist import WhitelistEntry
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.whitelist_repository import WhitelistRepository
from src.infrastructure.timezone import now_msk
from src.presentation.router_utils import register_or_get_user


@pytest.mark.asyncio
async def test_whitelist_create_and_get(session: AsyncSession) -> None:
    repo = WhitelistRepository(session)

    entry = WhitelistEntry(
        id=None,
        username="wheresyourego",
        full_name="Иван Иванов",
        role=UserRole.MEMBER,
        created_by=111,
        created_at=now_msk(),
    )
    created = await repo.create(entry)
    assert created.id is not None
    assert created.username == "wheresyourego"
    assert created.role == UserRole.MEMBER

    # Case-insensitive lookup with and without @
    found1 = await repo.get_by_username("@wheresyourego")
    found2 = await repo.get_by_username("WheresYourEgo")
    assert found1 is not None
    assert found2 is not None
    assert found1.id == created.id
    assert found2.id == created.id


@pytest.mark.asyncio
async def test_whitelist_mark_used(session: AsyncSession) -> None:
    repo = WhitelistRepository(session)

    entry = WhitelistEntry(
        id=None,
        username="rider_john",
        full_name="Джон Доу",
        role=UserRole.TREASURER,
        created_by=111,
        created_at=now_msk(),
    )
    created = await repo.create(entry)

    # Active pending invites list includes this entry
    pending = await repo.list_pending()
    assert any(p.id == created.id for p in pending)

    # Mark as used
    await repo.mark_used(created.id)

    # Now get_by_username should return None (not pending anymore)
    assert await repo.get_by_username("rider_john") is None

    # Pending list should no longer have it
    pending_after = await repo.list_pending()
    assert not any(p.id == created.id for p in pending_after)


@pytest.mark.asyncio
async def test_whitelist_delete(session: AsyncSession) -> None:
    repo = WhitelistRepository(session)

    entry = WhitelistEntry(
        id=None,
        username="mistake_user",
        full_name="Ошибочный ник",
        role=UserRole.MEMBER,
        created_by=111,
        created_at=now_msk(),
    )
    created = await repo.create(entry)
    assert await repo.get_by_username("mistake_user") is not None

    await repo.delete(created.id)
    assert await repo.get_by_username("mistake_user") is None


@pytest.mark.asyncio
async def test_register_or_get_user_with_whitelist(session: AsyncSession) -> None:
    wl_repo = WhitelistRepository(session)
    user_repo = UserRepository(session)

    # Pre-register user in whitelist
    await wl_repo.create(WhitelistEntry(
        id=None,
        username="motorider",
        full_name="Мотоциклист Боб",
        role=UserRole.TREASURER,
        created_by=999,
        created_at=now_msk(),
    ))

    # Mock Telegram message from @motorider
    message = MagicMock()
    message.from_user.id = 77712345
    message.from_user.username = "motorider"
    message.from_user.full_name = "Боб Смит"
    message.date = datetime.now()

    user = await register_or_get_user(message, session, admin_ids=[])
    assert user is not None
    assert user.telegram_id == 77712345
    assert user.username == "motorider"
    assert user.full_name == "Мотоциклист Боб"
    assert user.role == UserRole.TREASURER
    assert user.status == UserStatus.ACTIVE

    # Whitelist entry should now be marked as used
    assert await wl_repo.get_by_username("motorider") is None


@pytest.mark.asyncio
async def test_register_or_get_user_closed_club_reject(session: AsyncSession) -> None:
    # Unknown user not in admin_ids and not in whitelist
    message = MagicMock()
    message.from_user.id = 99999999
    message.from_user.username = "unknown_stranger"
    message.from_user.full_name = "Незнакомец"
    message.date = datetime.now()

    user = await register_or_get_user(message, session, admin_ids=[])
    assert user is None
