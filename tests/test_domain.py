"""Тесты domain-сущностей."""
from decimal import Decimal

from src.domain.entities.fine import Fine
from src.domain.entities.payment import Payment
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.domain.entities.user import User


# ─── User ──────────────────────────────────────────────────────────────────


def test_user_defaults():
    user = User()
    assert user.telegram_id == 0
    assert user.role == UserRole.MEMBER
    assert user.status == UserStatus.ACTIVE
    assert user.balance_credit == Decimal("0")
    assert user.id is None


def test_user_with_values():
    user = User(
        telegram_id=123,
        full_name="Иван Иванов",
        role=UserRole.TREASURER,
        status=UserStatus.ARCHIVED,
        balance_credit=Decimal("500.50"),
    )
    assert user.telegram_id == 123
    assert user.full_name == "Иван Иванов"
    assert user.role == UserRole.TREASURER
    assert user.status == UserStatus.ARCHIVED
    assert user.balance_credit == Decimal("500.50")


# ─── Fine ──────────────────────────────────────────────────────────────────


def test_fine_remaining_amount_full_paid():
    fine = Fine(user_id=1, amount=Decimal("500"), paid_amount=Decimal("500"))
    assert fine.remaining_amount == Decimal("0")


def test_fine_remaining_amount_partial():
    fine = Fine(user_id=1, amount=Decimal("500"), paid_amount=Decimal("200"))
    assert fine.remaining_amount == Decimal("300")


def test_fine_remaining_amount_none_paid():
    fine = Fine(user_id=1, amount=Decimal("500"), paid_amount=Decimal("0"))
    assert fine.remaining_amount == Decimal("500")


def test_fine_remaining_amount_overpaid():
    # paid_amount > amount → clamp to 0
    fine = Fine(user_id=1, amount=Decimal("500"), paid_amount=Decimal("600"))
    assert fine.remaining_amount == Decimal("0")


def test_fine_default_values():
    fine = Fine()
    assert fine.user_id == 0
    assert fine.amount == Decimal("0")
    assert fine.paid_amount == Decimal("0")
    assert fine.reason == ""
    assert fine.status == FineStatus.ACTIVE
    assert fine.id is None


# ─── Payment ───────────────────────────────────────────────────────────────


def test_payment_defaults():
    payment = Payment()
    assert payment.user_id == 0
    assert payment.amount == Decimal("0")
    assert payment.month == 0
    assert payment.year == 0
    assert payment.payment_type == "fee"
    assert payment.status == PaymentStatus.PENDING
    assert payment.id is None


def test_payment_with_values():
    payment = Payment(
        user_id=1,
        amount=Decimal("3500"),
        month=8,
        year=2026,
        payment_type="fine",
        status=PaymentStatus.CONFIRMED,
        comment="Оплата штрафа",
    )
    assert payment.user_id == 1
    assert payment.amount == Decimal("3500")
    assert payment.payment_type == "fine"
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.comment == "Оплата штрафа"
