"""
Конфигурация pytest: фикстуры БД, моки бота, настройки тестового окружения.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.domain.entities.fine import Fine
from src.domain.entities.payment import Payment
from src.domain.entities.user import User
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.base import Base
from src.infrastructure.database.models import (
    AuditLogModel,
    ExpenseModel,
    FineModel,
    MonthlyFeeModel,
    PaymentModel,
    UserModel,
)
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.infrastructure.repositories.expense_repository import ExpenseRepository
from src.infrastructure.repositories.fee_repository import FeeRepository
from src.infrastructure.repositories.fine_repository import FineRepository
from src.infrastructure.repositories.payment_repository import PaymentRepository
from src.infrastructure.repositories.user_repository import UserRepository


# ─── Фикстуры БД ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    """In-memory SQLite engine for tests."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        pool_pre_ping=True,
    )
    # Enable foreign keys for SQLite
    @event.listens_for(eng.sync_engine, "connect")
    def _set_foreign_keys(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provides an async session scoped to a single transaction."""
    link = engine.execution_options(set_connection_execution_options={"transaction_isolation": None})
    async_session = async_sessionmaker(link, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        async with s.begin():
            yield s


# ─── Фикстуры репозиториев ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def user_repo(session: AsyncSession) -> UserRepository:
    return UserRepository(session)


@pytest_asyncio.fixture
async def fine_repo(session: AsyncSession) -> FineRepository:
    return FineRepository(session)


@pytest_asyncio.fixture
async def payment_repo(session: AsyncSession) -> PaymentRepository:
    return PaymentRepository(session)


@pytest_asyncio.fixture
async def expense_repo(session: AsyncSession) -> ExpenseRepository:
    return ExpenseRepository(session)


@pytest_asyncio.fixture
async def audit_repo(session: AsyncSession) -> AuditLogRepository:
    return AuditLogRepository(session)


# ─── Фикстуры сущностей ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def active_user(user_repo: UserRepository) -> User:
    user = User(
        telegram_id=411356369,
        username="testuser",
        full_name="Тестовый Участник",
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        balance_credit=Decimal("1500.00"),
    )
    return await user_repo.create(user)


@pytest_asyncio.fixture
async def treasurer_user(user_repo: UserRepository) -> User:
    user = User(
        telegram_id=999888777,
        username="treasurertest",
        full_name="Тестовый Казначей",
        role=UserRole.TREASURER,
        status=UserStatus.ACTIVE,
    )
    return await user_repo.create(user)


@pytest_asyncio.fixture
async def admin_user(user_repo: UserRepository) -> User:
    user = User(
        telegram_id=111222333,
        username="admintest",
        full_name="Тестовый Админ",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    return await user_repo.create(user)


# ─── Фикстура мока бота ───────────────────────────────────────────────────


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.send_photo = AsyncMock(return_value=MagicMock(message_id=2))
    return bot


# ─── Утилиты ──────────────────────────────────────────────────────────────


def make_user(
    telegram_id: int = 12345,
    role: UserRole = UserRole.MEMBER,
    status: UserStatus = UserStatus.ACTIVE,
    balance: Decimal = Decimal("0"),
    **kwargs,
) -> User:
    return User(
        telegram_id=telegram_id,
        full_name=kwargs.get("full_name", f"User_{telegram_id}"),
        username=kwargs.get("username", f"user{telegram_id}"),
        role=role,
        status=status,
        balance_credit=balance,
    )


def make_fine(
    user_id: int = 1,
    amount: Decimal = Decimal("500"),
    status: FineStatus = FineStatus.ACTIVE,
    **kwargs,
) -> Fine:
    return Fine(
        user_id=user_id,
        amount=amount,
        reason=kwargs.get("reason", "тест"),
        paid_amount=kwargs.get("paid_amount", Decimal("0")),
        status=status,
        issued_by=kwargs.get("issued_by", 0),
    )


def make_payment(
    user_id: int = 1,
    amount: Decimal = Decimal("1000"),
    month: int = 8,
    year: int = 2026,
    status: PaymentStatus = PaymentStatus.PENDING,
    ptype: str = "fee",
    **kwargs,
) -> Payment:
    return Payment(
        user_id=user_id,
        amount=amount,
        month=month,
        year=year,
        payment_type=ptype,
        status=status,
        comment=kwargs.get("comment"),
        receipt_photo_id=kwargs.get("receipt_photo_id"),
        confirmed_by=kwargs.get("confirmed_by"),
    )
