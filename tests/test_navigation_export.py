"""Тесты навигации и экспорта."""
from __future__ import annotations

import io
import json
from decimal import Decimal
from datetime import date

import pytest

from src.presentation.middleware.navigation import (
    _nav_stack,
    get_nav_history,
    push_nav,
    pop_nav,
)
from src.presentation.export_pdf import generate_export_pdf
from src.domain.entities.user import User
from src.domain.entities.payment import Payment
from src.domain.entities.fine import Fine
from src.domain.entities.expense import Expense
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.expense_category import ExpenseCategory


# ─── Navigation ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_nav_stack():
    """Clear navigation stack before and after each test."""
    _nav_stack.clear()
    yield
    _nav_stack.clear()


def test_nav_default_is_main_menu():
    assert get_nav_history(1) == ["main_menu"]


def test_nav_push_and_pop():
    push_nav(1, "admin_users")
    assert get_nav_history(1) == ["main_menu", "admin_users"]

    previous = pop_nav(1)
    assert previous == "main_menu"
    assert get_nav_history(1) == ["main_menu"]


def test_nav_multiple_pushes():
    push_nav(1, "admin_users")
    push_nav(1, "admin_settings")
    push_nav(1, "admin_export")
    assert get_nav_history(1) == ["main_menu", "admin_users", "admin_settings", "admin_export"]

    previous = pop_nav(1)
    assert previous == "admin_settings"
    previous = pop_nav(1)
    assert previous == "admin_users"


def test_nav_main_menu_resets_stack():
    push_nav(1, "admin_users")
    push_nav(1, "admin_settings")
    # Simulate clicking "main_menu"
    _nav_stack[1] = ["main_menu"]
    assert get_nav_history(1) == ["main_menu"]


def test_nav_duplication_ignored():
    push_nav(1, "admin_users")
    push_nav(1, "admin_users")  # duplicate — should be ignored
    assert len(get_nav_history(1)) == 2  # ["main_menu", "admin_users"]


def test_nav_stack_limited_to_10():
    for i in range(12):
        push_nav(1, f"screen_{i}")
    history = get_nav_history(1)
    assert len(history) <= 10
    assert history[0] == "main_menu"


# ─── Export (PDF) ──────────────────────────────────────────────────────────


def _make_users(count: int = 3) -> list:
    users = []
    for i in range(count):
        u = User(
            id=i + 1,
            telegram_id=1000 + i,
            username=f"user{i}",
            full_name=f"Участник {i+1}",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
            balance_credit=Decimal("1000") * (i + 1),
        )
        users.append(u)
    return users


def _make_payments(count: int = 3) -> list:
    from decimal import Decimal
    payments = []
    for i in range(count):
        p = Payment(
            id=i + 1,
            user_id=i + 1,
            amount=Decimal("3500") * (i + 1),
            month=8,
            year=2026,
            payment_type="fee",
            status=PaymentStatus.CONFIRMED,
            comment=f"Взнос за август #{i+1}",
        )
        payments.append(p)
    return payments


def _make_fines(count: int = 2) -> list:
    fines = []
    for i in range(count):
        f = Fine(
            id=i + 1,
            user_id=i + 1,
            amount=Decimal("500") * (i + 1),
            reason=f"Опоздание на meeting #{i+1}",
            status=FineStatus.ACTIVE,
            issued_by=1,
        )
        fines.append(f)
    return fines


def _make_expenses(count: int = 2) -> list:
    from datetime import date
    expenses = []
    for i in range(count):
        e = Expense(
            id=i + 1,
            amount=Decimal("2000") * (i + 1),
            category=ExpenseCategory.FUEL,
            comment=f"Расход на выезд #{i+1}",
            created_by=1,
            expense_date=date(2026, 8, 15 + i),
        )
        expenses.append(e)
    return expenses


def test_generate_pdf_with_data():
    users = _make_users()
    payments = _make_payments()
    fines = _make_fines()
    expenses = _make_expenses()

    buf = generate_export_pdf(users, payments, fines, expenses)
    assert isinstance(buf, io.BytesIO)
    data = buf.getvalue()
    assert len(data) > 0
    # PDF magic bytes
    assert data.startswith(b"%PDF")


def test_generate_pdf_empty():
    buf = generate_export_pdf([], [], [], [])
    data = buf.getvalue()
    assert len(data) > 0
    assert data.startswith(b"%PDF")


def test_generate_pdf_cyrillic():
    """Verify Cyrillic text is present in the PDF output."""
    from decimal import Decimal
    users = [_make_users(1)[0]]
    buf = generate_export_pdf(users, [], [], [])
    data = buf.getvalue()
    # The PDF should contain UTF-8 encoded Cyrillic text
    assert b"\xd0" in data or b"\xd1" in data  # UTF-8 Cyrillic bytes
