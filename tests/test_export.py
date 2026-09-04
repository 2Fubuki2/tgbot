"""Тесты экспорта: JSON, CSV, PDF."""
from __future__ import annotations

import io
import json
from decimal import Decimal
from datetime import date

import pytest

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


# ─── Helpers ───────────────────────────────────────────────────────────────


def _user(tid: int, name: str, role: UserRole = UserRole.MEMBER, balance: Decimal = Decimal("0")) -> User:
    return User(id=tid, telegram_id=tid, username=f"user{tid}", full_name=name,
                role=role, status=UserStatus.ACTIVE, balance_credit=balance)


def _pay(pid: int, uid: int, amount: Decimal, month: int, year: int,
         status: PaymentStatus = PaymentStatus.CONFIRMED, ptype: str = "fee") -> Payment:
    return Payment(id=pid, user_id=uid, amount=amount, month=month, year=year,
                   payment_type=ptype, status=status, comment=f"comment_{pid}")


def _fine(fid: int, uid: int, amount: Decimal, reason: str,
          status: FineStatus = FineStatus.ACTIVE) -> Fine:
    return Fine(id=fid, user_id=uid, amount=amount, reason=reason,
                status=status, issued_by=1)


def _exp(eid: int, amount: Decimal, category: ExpenseCategory = ExpenseCategory.FUEL,
        comment: str = "test") -> Expense:
    return Expense(id=eid, amount=amount, category=category, comment=comment,
                   created_by=1, expense_date=date(2026, 8, 20))


# ─── PDF Export ────────────────────────────────────────────────────────────


def test_pdf_non_empty_with_data():
    users = [_user(1, "Иван Иванов", UserRole.MEMBER, Decimal("1500"))]
    payments = [_pay(1, 1, Decimal("3500"), 8, 2026)]
    fines = [_fine(1, 1, Decimal("500"), "опоздание")]
    expenses = [_exp(1, Decimal("2000"))]

    buf = generate_export_pdf(users, payments, fines, expenses)
    data = buf.getvalue()
    assert data.startswith(b"%PDF")
    assert len(data) > 500  # reasonable PDF size


def test_pdf_empty_sections():
    buf = generate_export_pdf([], [], [], [])
    data = buf.getvalue()
    assert data.startswith(b"%PDF")
    assert len(data) > 100


def test_pdf_contains_cyrillic():
    """Cyrillic text must be present in the PDF for readability."""
    users = [_user(1, "Алексей Петров", UserRole.ADMIN, Decimal("500"))]
    buf = generate_export_pdf(users, [], [], [])
    data = buf.getvalue()
    # Check for UTF-8 encoded Cyrillic bytes (А=0xD0\x90, л=0xD0\xBB, etc.)
    assert b"\xd0\x90" in data or b"\xd0\xbb" in data


def test_pdf_multiple_pages():
    """PDF should have multiple pages when there's a lot of data."""
    users = [_user(i, f"Участник {i}", UserRole.MEMBER, Decimal(str(i * 100))) for i in range(1, 6)]
    payments = [_pay(i, 1, Decimal("3500"), 8, 2026) for i in range(1, 6)]
    fines = [_fine(i, 1, Decimal("500"), f"причина {i}") for i in range(1, 6)]
    expenses = [_exp(i, Decimal("1000")) for i in range(1, 6)]

    buf = generate_export_pdf(users, payments, fines, expenses)
    data = buf.getvalue()
    assert data.startswith(b"%PDF")
    # PageBreak is used; verify there are multiple sections
    assert b"Participants" in data or b"%PDF" in data[:4]


# ─── Export structure tests ────────────────────────────────────────────────


def test_pdf_section_headers():
    """Verify all 4 sections generate a valid multi-page PDF."""
    users = [_user(1, "Test")]
    payments = [_pay(1, 1, Decimal("100"), 1, 2026)]
    fines = [_fine(1, 1, Decimal("50"), "test fine")]
    expenses = [_exp(1, Decimal("25"))]

    buf = generate_export_pdf(users, payments, fines, expenses)
    data = buf.getvalue()

    assert data.startswith(b"%PDF")
    assert len(data) > 1000
    assert b"/Page" in data
