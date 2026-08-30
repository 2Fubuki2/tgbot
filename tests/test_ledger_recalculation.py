"""Тесты пересчёта баланса пользователя (balance recalculation)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.infrastructure.database.base import Base
from src.infrastructure.database.models.user import UserModel
from src.infrastructure.database.models.payment import PaymentModel
from src.infrastructure.database.models.monthly_fee import MonthlyFeeModel
from src.infrastructure.database.models.fine import FineModel
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.payment_repository import PaymentRepository
from src.infrastructure.repositories.fee_repository import FeeRepository
from src.infrastructure.repositories.fine_repository import FineRepository
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.fee_status import FeeStatus
from src.domain.value_objects.fine_status import FineStatus
from src.domain.entities.user import User
from src.domain.value_objects.user_status import UserStatus
from src.domain.entities.payment import Payment
from src.domain.entities.monthly_fee import MonthlyFee
from src.domain.entities.fine import Fine


def _make_async_db():
    """Создать In-Memory SQLite для тестов."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    return engine


@pytest.fixture
async def db_session():
    engine = _make_async_db()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    yield session
    await session.close()
    await engine.dispose()


async def _create_user(session, telegram_id: int = 12345, role="member") -> User:
    from src.domain.value_objects.role import UserRole
    user = User(
        telegram_id=telegram_id,
        full_name="Test User",
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
    )
    repo = UserRepository(session)
    return await repo.create(user)


async def _create_payment(session, user_id: int, amount: Decimal, ptype: str = "fee",
                           status: PaymentStatus = PaymentStatus.CONFIRMED) -> Payment:
    payment = Payment(
        user_id=user_id,
        amount=amount,
        payment_date=datetime(2024, 8, 30, tzinfo=timezone(timedelta(hours=3))),
        month=8,
        year=2024,
        payment_type=ptype,
        status=status,
    )
    repo = PaymentRepository(session)
    return await repo.create(payment)


async def _create_fee(session, user_id: int, amount: Decimal, month: int, year: int,
                       status: FeeStatus = FeeStatus.PENDING) -> MonthlyFee:
    fee = MonthlyFee(
        user_id=user_id,
        amount=amount,
        month=month,
        year=year,
        status=status,
    )
    repo = FeeRepository(session)
    return await repo.create(fee)


async def _create_fine(session, user_id: int, amount: Decimal, reason: str = "тест") -> Fine:
    fine = Fine(
        user_id=user_id,
        amount=amount,
        reason=reason,
        status=FineStatus.ACTIVE,
    )
    repo = FineRepository(session)
    return await repo.create(fine)


class TestBalanceRecalculation:
    """Тесты пересчёта баланса из подтверждённых платежей и оплаченных взносов."""

    async def test_balance_from_payments_and_fees(self, db_session):
        """Баланс = сумма подтверждённых fee-платежей - сумма оплаченных взносов."""
        user = await _create_user(db_session)
        await _create_payment(db_session, user.id, Decimal("3000"))
        await _create_fee(db_session, user.id, Decimal("1000"), 6, 2024, FeeStatus.PAID)
        await _create_fee(db_session, user.id, Decimal("1000"), 7, 2024, FeeStatus.PAID)

        from src.presentation.handlers.ledger_edit import _recalculate_balance
        balance = await _recalculate_balance(db_session, user.id)

        assert balance == Decimal("1000"), f"Expected 1000, got {balance}"

    async def test_no_payments_no_fees(self, db_session):
        """Нет платежей и взносов → баланс 0."""
        user = await _create_user(db_session)

        from src.presentation.handlers.ledger_edit import _recalculate_balance
        balance = await _recalculate_balance(db_session, user.id)

        assert balance == Decimal("0")

    async def test_only_pending_fees_no_balance(self, db_session):
        """Только ожидающие взносы → баланс 0 (не оплачены)."""
        user = await _create_user(db_session)
        await _create_fee(db_session, user.id, Decimal("1000"), 8, 2024, FeeStatus.PENDING)

        from src.presentation.handlers.ledger_edit import _recalculate_balance
        balance = await _recalculate_balance(db_session, user.id)

        assert balance == Decimal("0")

    async def test_payment_minus_fully_paid_fees(self, db_session):
        """Платёж 5000₽, два оплаченных взноса по 2000₽ → баланс 1000₽."""
        user = await _create_user(db_session)
        await _create_payment(db_session, user.id, Decimal("5000"))
        await _create_fee(db_session, user.id, Decimal("2000"), 6, 2024, FeeStatus.PAID)
        await _create_fee(db_session, user.id, Decimal("2000"), 7, 2024, FeeStatus.PAID)

        from src.presentation.handlers.ledger_edit import _recalculate_balance
        balance = await _recalculate_balance(db_session, user.id)

        assert balance == Decimal("1000")

    async def test_fully_paid_fees_zero_balance(self, db_session):
        """Платёж 2000₽, два оплаченных взноса по 1000₽ → баланс 0."""
        user = await _create_user(db_session)
        await _create_payment(db_session, user.id, Decimal("2000"))
        await _create_fee(db_session, user.id, Decimal("1000"), 6, 2024, FeeStatus.PAID)
        await _create_fee(db_session, user.id, Decimal("1000"), 7, 2024, FeeStatus.PAID)

        from src.presentation.handlers.ledger_edit import _recalculate_balance
        balance = await _recalculate_balance(db_session, user.id)

        assert balance == Decimal("0")

    async def test_rejected_payment_not_counted(self, db_session):
        """Отклонённый платёж не учитывается в балансе."""
        user = await _create_user(db_session)
        await _create_payment(db_session, user.id, Decimal("1000"), status=PaymentStatus.REJECTED)
        await _create_payment(db_session, user.id, Decimal("5000"), status=PaymentStatus.CONFIRMED)

        from src.presentation.handlers.ledger_edit import _recalculate_balance
        balance = await _recalculate_balance(db_session, user.id)

        assert balance == Decimal("5000")


class TestFinePaidRecalculation:
    """Тесты пересчёта paid_amount у штрафов."""

    async def test_recalculate_fine_paid_amounts(self, db_session):
        """При удалении/изменении fine-платежей paid_amount пересчитывается."""
        user = await _create_user(db_session)
        fine = await _create_fine(db_session, user.id, Decimal("3000"))

        # Create two fine payments that sum to more than the fine
        await _create_payment(db_session, user.id, Decimal("2000"), ptype="fine")
        await _create_payment(db_session, user.id, Decimal("2000"), ptype="fine")

        from src.presentation.handlers.ledger_edit import _recalculate_fine_paid_amounts
        await _recalculate_fine_paid_amounts(db_session, user.id)

        # Refresh fine
        fine_repo = FineRepository(db_session)
        fine = await fine_repo.get_by_id(fine.id)
        assert fine is not None
        assert fine.paid_amount == Decimal("3000"), f"Expected 3000, got {fine.paid_amount}"
        assert fine.status == FineStatus.CANCELLED

    async def test_fine_fully_paid(self, db_session):
        """Два платежа по 1500₽ на штраф 3000₽ → fine fully paid."""
        user = await _create_user(db_session)
        await _create_fine(db_session, user.id, Decimal("3000"))
        await _create_payment(db_session, user.id, Decimal("1500"), ptype="fine")
        await _create_payment(db_session, user.id, Decimal("1500"), ptype="fine")

        from src.presentation.handlers.ledger_edit import _recalculate_fine_paid_amounts
        await _recalculate_fine_paid_amounts(db_session, user.id)

        fine_repo = FineRepository(db_session)
        fines = await fine_repo.list_by_user(user.id)
        assert len(fines) == 1
        assert fines[0].paid_amount == Decimal("3000")
        assert fines[0].status == FineStatus.CANCELLED
