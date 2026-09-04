from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, User as TgUser

from src.domain.entities.fine import Fine
from src.domain.entities.monthly_fee import MonthlyFee
from src.domain.entities.payment import Payment
from src.domain.entities.user import User
from src.domain.entities.whitelist import WhitelistEntry
from src.domain.value_objects.fee_status import FeeStatus
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.models.audit_log import AuditLogModel
from src.infrastructure.repositories.fee_repository import FeeRepository
from src.infrastructure.repositories.fine_repository import FineRepository
from src.infrastructure.repositories.payment_repository import PaymentRepository
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.whitelist_repository import WhitelistRepository
from src.presentation.middleware.user_access import UserAccessMiddleware
from src.presentation.router_utils import register_or_get_user


@pytest.mark.asyncio
async def test_hard_delete_cleans_all_user_dependencies(session):
    u_repo = UserRepository(session)
    fee_repo = FeeRepository(session)
    fine_repo = FineRepository(session)
    pay_repo = PaymentRepository(session)
    wl_repo = WhitelistRepository(session)

    # 1. Create admin user and target user
    admin_user = await u_repo.create(User(
        id=None,
        telegram_id=9999001,
        username="admin1",
        full_name="Admin",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    ))
    target_user = await u_repo.create(User(
        id=None,
        telegram_id=9999002,
        username="deleted_user",
        full_name="Target User",
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
    ))

    # 2. Add dependencies for target user
    await fee_repo.create(MonthlyFee(
        user_id=target_user.id,
        amount=Decimal("1000.00"),
        month=1,
        year=2026,
        status=FeeStatus.PENDING,
    ))
    await fine_repo.create(Fine(
        user_id=target_user.id,
        amount=Decimal("500.00"),
        reason="Test fine",
        issued_by=admin_user.id,
        status=FineStatus.ACTIVE,
    ))
    await pay_repo.create(Payment(
        user_id=target_user.id,
        amount=Decimal("1000.00"),
        payment_date=date.today(),
        month=1,
        year=2026,
        payment_type="fee",
        status=PaymentStatus.CONFIRMED,
        confirmed_by=admin_user.id,
    ))
    await wl_repo.create(WhitelistEntry(
        username="deleted_user",
        full_name="Target User",
        role=UserRole.MEMBER,
        created_by=admin_user.telegram_id,
        is_used=True,
    ))

    # Add audit log for target user
    audit_entry = AuditLogModel(
        user_id=target_user.id,
        action="test_action",
        entity_type="user",
        entity_id=target_user.id,
        details="{}",
    )
    session.add(audit_entry)
    await session.flush()

    # 3. Perform hard delete
    await u_repo.hard_delete(target_user.id)

    # 4. Verify target user is gone
    deleted = await u_repo.get_by_id(target_user.id)
    assert deleted is None

    # Verify fees, fines, payments, and whitelist entry are gone
    fees = await fee_repo.list_by_user(target_user.id)
    assert len(fees) == 0

    fines = await fine_repo.list_by_user(target_user.id)
    assert len(fines) == 0

    payments = await pay_repo.list_by_user(target_user.id)
    assert len(payments) == 0

    wl = await wl_repo.get_by_username("deleted_user")
    assert wl is None


@pytest.mark.asyncio
async def test_reactivate_expelled_user_via_whitelist(session):
    u_repo = UserRepository(session)
    wl_repo = WhitelistRepository(session)

    # 1. Create an expelled user
    user = await u_repo.create(User(
        id=None,
        telegram_id=8888001,
        username="expelled_guy",
        full_name="Old Name",
        role=UserRole.MEMBER,
        status=UserStatus.EXPELLED,
    ))

    # 2. Admin creates a new whitelist invite for his username
    invite = await wl_repo.create(WhitelistEntry(
        username="expelled_guy",
        full_name="New Name",
        role=UserRole.TREASURER,
        created_by=111111,
    ))

    # 3. User sends /start
    msg = MagicMock(spec=Message)
    msg.from_user = TgUser(id=8888001, is_bot=False, first_name="New Name", username="expelled_guy")
    msg.date = datetime.now()

    reactivated = await register_or_get_user(msg, session, admin_ids=[])

    assert reactivated is not None
    assert reactivated.status == UserStatus.ACTIVE
    assert reactivated.role == UserRole.TREASURER
    assert reactivated.full_name == "New Name"

    # Verify invite is marked used (no longer returned by get_by_username which checks is_used=False)
    inv_check = await wl_repo.get_by_username("expelled_guy")
    assert inv_check is None


@pytest.mark.asyncio
async def test_user_access_middleware_blocks_expelled(session):
    u_repo = UserRepository(session)
    await u_repo.create(User(
        id=None,
        telegram_id=7777001,
        username="blocked_user",
        full_name="Blocked",
        role=UserRole.MEMBER,
        status=UserStatus.EXPELLED,
    ))

    middleware = UserAccessMiddleware()
    handler = AsyncMock()

    # Message event
    msg = MagicMock(spec=Message)
    msg.text = "💰 Мой бюджет"
    msg.answer = AsyncMock()

    data = {
        "event_from_user": TgUser(id=7777001, is_bot=False, first_name="Blocked", username="blocked_user"),
    }

    # Handler should NOT be called
    await middleware(handler, msg, data)
    assert not handler.called
    assert msg.answer.called
    assert isinstance(msg.answer.call_args[1]["reply_markup"], ReplyKeyboardRemove)


@pytest.mark.asyncio
async def test_user_access_middleware_allows_start(session):
    middleware = UserAccessMiddleware()
    handler = AsyncMock(return_value="OK")

    msg = MagicMock(spec=Message)
    msg.text = "/start"
    msg.answer = AsyncMock()

    data = {
        "event_from_user": TgUser(id=6666001, is_bot=False, first_name="Newbie", username="newbie"),
    }

    result = await middleware(handler, msg, data)
    assert handler.called
    assert result == "OK"
