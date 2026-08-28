"""Тесты репозиториев (UserRepository, FineRepository, PaymentRepository, ExpenseRepository)."""
import pytest
from decimal import Decimal

from src.domain.entities.user import User
from src.domain.entities.fine import Fine
from src.domain.entities.payment import Payment
from src.domain.entities.expense import Expense
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.domain.value_objects.expense_category import ExpenseCategory


# ─── UserRepository ────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_create_and_get_by_id(user_repo, active_user):
    retrieved = await user_repo.get_by_id(active_user.id)
    assert retrieved is not None
    assert retrieved.telegram_id == active_user.telegram_id
    assert retrieved.full_name == "Тестовый Участник"
    assert retrieved.role == UserRole.MEMBER


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_get_by_telegram_id(user_repo, active_user):
    retrieved = await user_repo.get_by_telegram_id(active_user.telegram_id)
    assert retrieved is not None
    assert retrieved.id == active_user.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_get_by_telegram_id_not_found(user_repo):
    retrieved = await user_repo.get_by_telegram_id(99999999)
    assert retrieved is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_list_active(user_repo, active_user, treasurer_user, admin_user):
    users = await user_repo.list_active()
    ids = {u.id for u in users}
    assert active_user.id in ids
    assert treasurer_user.id in ids
    assert admin_user.id in ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_search_by_name(user_repo, active_user):
    results = await user_repo.search("Тестовый")
    assert len(results) >= 1
    assert any(u.telegram_id == active_user.telegram_id for u in results)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_search_by_username(user_repo, active_user):
    results = await user_repo.search("testuser")
    assert len(results) >= 1
    assert results[0].username == "testuser"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_update(user_repo, active_user):
    active_user.full_name = "Новое Имя"
    active_user.balance_credit = Decimal("2000.00")
    updated = await user_repo.update(active_user)
    assert updated.full_name == "Новое Имя"
    assert updated.balance_credit == Decimal("2000.00")

    # Verify persistence
    reloaded = await user_repo.get_by_id(active_user.id)
    assert reloaded.full_name == "Новое Имя"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_soft_delete(user_repo, active_user):
    user_id = active_user.id
    await user_repo.delete(user_id)

    # Should be expeled, not gone
    reloaded = await user_repo.get_by_id(user_id)
    assert reloaded is not None
    assert reloaded.status == UserStatus.EXPELLED
    assert reloaded.role == UserRole.MEMBER


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_hard_delete(user_repo, active_user):
    user_id = active_user.id
    await user_repo.hard_delete(user_id)
    reloaded = await user_repo.get_by_id(user_id)
    assert reloaded is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_count_active(user_repo, active_user, treasurer_user):
    count = await user_repo.count_active()
    assert count == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_list_by_role(user_repo, active_user, treasurer_user, admin_user):
    members = await user_repo.list_by_role(UserRole.MEMBER)
    assert any(u.telegram_id == active_user.telegram_id for u in members)
    assert not any(u.telegram_id == treasurer_user.telegram_id for u in members)

    treasurers = await user_repo.list_by_role(UserRole.TREASURER)
    assert any(u.telegram_id == treasurer_user.telegram_id for u in treasurers)


# ─── FineRepository ────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fine_create_and_get(fine_repo, active_user):
    fine = Fine(
        user_id=active_user.id,
        amount=Decimal("500"),
        reason="опоздание",
        issued_by=active_user.id,
    )
    created = await fine_repo.create(fine)
    assert created.id is not None
    assert created.amount == Decimal("500")
    assert created.status == FineStatus.ACTIVE

    retrieved = await fine_repo.get_by_id(created.id)
    assert retrieved is not None
    assert retrieved.reason == "опоздание"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fine_list_active(fine_repo, active_user):
    f1 = Fine(user_id=active_user.id, amount=Decimal("300"), reason="штраф1", issued_by=active_user.id)
    f2 = Fine(user_id=active_user.id, amount=Decimal("200"), reason="штраф2", issued_by=active_user.id)
    await fine_repo.create(f1)
    await fine_repo.create(f2)

    active = await fine_repo.list_active()
    assert len(active) == 2
    assert all(f.status == FineStatus.ACTIVE for f in active)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fine_list_active_excludes_paid(fine_repo, active_user):
    fully_paid = Fine(
        user_id=active_user.id, amount=Decimal("500"), paid_amount=Decimal("500"),
        reason="полностью оплачен", issued_by=active_user.id,
    )
    await fine_repo.create(fully_paid)

    active = await fine_repo.list_active()
    assert len(active) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fine_list_active_excludes_cancelled(fine_repo, active_user):
    cancelled = Fine(
        user_id=active_user.id, amount=Decimal("500"),
        reason="отменён", issued_by=active_user.id,
        status=FineStatus.CANCELLED,
    )
    await fine_repo.create(cancelled)

    active = await fine_repo.list_active()
    assert len(active) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fine_total_active_amount(fine_repo, active_user):
    f1 = Fine(user_id=active_user.id, amount=Decimal("300"), reason="a", issued_by=active_user.id)
    f2 = Fine(user_id=active_user.id, amount=Decimal("200"), reason="b", issued_by=active_user.id)
    await fine_repo.create(f1)
    await fine_repo.create(f2)

    total = await fine_repo.total_active_amount()
    assert total == Decimal("500")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fine_update(fine_repo, active_user):
    fine = Fine(user_id=active_user.id, amount=Decimal("500"), reason="test", issued_by=active_user.id)
    created = await fine_repo.create(fine)

    created.paid_amount = Decimal("200")
    updated = await fine_repo.update(created)
    assert updated.paid_amount == Decimal("200")


# ─── PaymentRepository ─────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_payment_create_and_get(payment_repo, active_user):
    pay = Payment(
        user_id=active_user.id, amount=Decimal("3500"),
        month=8, year=2026, payment_type="fee",
    )
    created = await payment_repo.create(pay)
    assert created.id is not None
    assert created.amount == Decimal("3500")
    assert created.status == PaymentStatus.PENDING

    retrieved = await payment_repo.get_by_id(created.id)
    assert retrieved is not None
    assert retrieved.year == 2026


@pytest.mark.integration
@pytest.mark.asyncio
async def test_payment_list_pending(payment_repo, active_user):
    p1 = Payment(user_id=active_user.id, amount=Decimal("1000"), month=7, year=2026)
    p2 = Payment(user_id=active_user.id, amount=Decimal("2000"), month=8, year=2026)
    await payment_repo.create(p1)
    await payment_repo.create(p2)

    pending = await payment_repo.list_pending()
    assert len(pending) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_payment_list_confirmed(payment_repo, active_user):
    p = Payment(user_id=active_user.id, amount=Decimal("1000"), month=8, year=2026,
                status=PaymentStatus.CONFIRMED, confirmed_by=active_user.id)
    created = await payment_repo.create(p)

    # Update to confirmed
    created.status = PaymentStatus.CONFIRMED
    await payment_repo.update(created)

    confirmed = await payment_repo.list_confirmed()
    assert len(confirmed) == 1
    assert confirmed[0].id == created.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_payment_total_confirmed(payment_repo, active_user):
    p1 = Payment(user_id=active_user.id, amount=Decimal("1000"), month=7, year=2026,
                 status=PaymentStatus.CONFIRMED)
    p2 = Payment(user_id=active_user.id, amount=Decimal("500"), month=8, year=2026,
                 status=PaymentStatus.CONFIRMED)
    await payment_repo.create(p1)
    await payment_repo.create(p2)

    total = await payment_repo.total_confirmed_amount()
    assert total == Decimal("1500")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_payment_count_pending(payment_repo, active_user):
    for i in range(3):
        await payment_repo.create(Payment(user_id=active_user.id, amount=Decimal("100"), month=8, year=2026))
    count = await payment_repo.count_pending()
    assert count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_payment_list_by_month(payment_repo, active_user):
    p_july = Payment(user_id=active_user.id, amount=Decimal("1000"), month=7, year=2026)
    p_aug = Payment(user_id=active_user.id, amount=Decimal("2000"), month=8, year=2026)
    await payment_repo.create(p_july)
    await payment_repo.create(p_aug)

    aug_payments = await payment_repo.list_by_month(8, 2026)
    assert len(aug_payments) == 1
    assert aug_payments[0].amount == Decimal("2000")


# ─── ExpenseRepository ─────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_expense_create_and_list(expense_repo, active_user):
    exp = Expense(
        amount=Decimal("5000"),
        category=ExpenseCategory.FUEL,
        comment="Бензин на выезд",
        created_by=active_user.id,
        expense_date="2026-08-15",
    )
    created = await expense_repo.create(exp)
    assert created.id is not None

    all_expenses = await expense_repo.list_all()
    assert len(all_expenses) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_expense_total_amount(expense_repo, active_user):
    e1 = Expense(amount=Decimal("1000"), created_by=active_user.id)
    e2 = Expense(amount=Decimal("2000"), created_by=active_user.id)
    await expense_repo.create(e1)
    await expense_repo.create(e2)

    total = await expense_repo.total_amount()
    assert total == Decimal("3000")
