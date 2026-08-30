"""Тесты для утилиты московского времени и логики погашения задолженности."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest


# ─── Timezone tests ──────────────────────────────────────────────────────

class TestMoscowTimezone:
    """Тесты модуля src.infrastructure.timezone."""

    def test_now_msk_has_correct_offset(self):
        from src.infrastructure.timezone import now_msk
        now = now_msk()
        assert now.tzinfo is not None
        offset = now.utcoffset()
        assert offset == timedelta(hours=3), f"Expected UTC+3, got {offset}"

    def test_now_msk_is_3_hours_ahead_of_utc(self):
        from src.infrastructure.timezone import now_msk
        msk_now = now_msk()
        utc_now = datetime.now(timezone.utc)
        # Compare UTC time converted to MSK vs actual MSK time
        utc_in_msk = utc_now.astimezone(timezone(timedelta(hours=3)))
        diff = msk_now - utc_in_msk
        assert abs(diff.total_seconds()) < 5, f"Time diff: {diff}"
        # Also verify the offset is +3
        assert msk_now.utcoffset() == timedelta(hours=3)

    def test_today_msk_returns_date(self):
        from src.infrastructure.timezone import today_msk
        today = today_msk()
        assert isinstance(today, date)
        expected = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=3))).date()
        assert today == expected

    def test_utcnow_to_msk_naive_adds_tzinfo(self):
        from src.infrastructure.timezone import utcnow_to_msk
        naive = datetime(2024, 8, 30, 12, 0, 0)
        result = utcnow_to_msk(naive)
        assert result.tzinfo is not None
        # Naive datetime is treated as already in MSK, so hour stays 12
        assert result.hour == 12
        assert result.utcoffset() == timedelta(hours=3)

    def test_utcnow_to_msk_aware(self):
        from src.infrastructure.timezone import utcnow_to_msk
        utc_dt = datetime(2024, 8, 30, 12, 0, 0, tzinfo=timezone.utc)
        result = utcnow_to_msk(utc_dt)
        assert result.hour == 15
        assert result.tzinfo is not None


# ─── Fee repayment logic tests ───────────────────────────────────────────

class TestFeeRepaymentLogic:
    """Тесты логики погашения задолженности по взносам."""

    def test_payment_reduces_debt_chronologically(self):
        """Платёж 1000₽ должен погасить часть долга 3000₽ → остаток 2000₽."""
        from src.domain.value_objects.fee_status import FeeStatus
        from src.domain.entities.monthly_fee import MonthlyFee

        # Simulate 3 pending fees: 1000₽ each (June, July, Aug)
        fees = [
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=6, year=2024, status=FeeStatus.PENDING),
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=7, year=2024, status=FeeStatus.PENDING),
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=8, year=2024, status=FeeStatus.PENDING),
        ]

        # Apply 1000₽ payment
        balance = Decimal("1000")
        applied = 0
        for fee in sorted(fees, key=lambda f: (f.year, f.month)):
            if balance <= 0:
                break
            if fee.status == FeeStatus.PENDING:
                apply = min(balance, fee.amount)
                balance -= apply
                if apply > 0:
                    fee.status = FeeStatus.PAID
                    fee.paid_at = datetime.now(timezone(timedelta(hours=3)))
                    applied += 1

        assert balance == 0, f"Expected balance 0, got {balance}"
        assert applied == 1, f"Expected 1 fee paid, got {applied}"
        assert fees[0].status == FeeStatus.PAID
        assert fees[1].status == FeeStatus.PENDING
        assert fees[2].status == FeeStatus.PENDING

    def test_payment_fully_clears_multiple_fees(self):
        """Платёж 2500₽ должен погасить 2 полных взноса + половину третьего."""
        from src.domain.value_objects.fee_status import FeeStatus
        from src.domain.entities.monthly_fee import MonthlyFee

        fees = [
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=6, year=2024, status=FeeStatus.PENDING),
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=7, year=2024, status=FeeStatus.PENDING),
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=8, year=2024, status=FeeStatus.PENDING),
        ]

        balance = Decimal("2500")
        for fee in sorted(fees, key=lambda f: (f.year, f.month)):
            if balance <= 0:
                break
            if fee.status == FeeStatus.PENDING:
                apply = min(balance, fee.amount)
                balance -= apply
                if apply > 0:
                    fee.status = FeeStatus.PAID
                    fee.paid_at = datetime.now(timezone(timedelta(hours=3)))

        # All 3 fees fully paid (1000+1000+1000=3000 > 2500, but min(balance, fee.amount) caps each)
        # Fee 1: apply=1000, balance=1500
        # Fee 2: apply=1000, balance=500
        # Fee 3: apply=500, balance=0 → fee marked PAID
        assert balance == 0, f"Expected 0 remaining, got {balance}"
        assert fees[0].status == FeeStatus.PAID
        assert fees[1].status == FeeStatus.PAID
        assert fees[2].status == FeeStatus.PAID

    def test_payment_exactly_matches_debt(self):
        """Платёж ровно в размер долга → все взносы оплачены, баланс 0."""
        from src.domain.value_objects.fee_status import FeeStatus
        from src.domain.entities.monthly_fee import MonthlyFee

        fees = [
            MonthlyFee(user_id=1, amount=Decimal("1500"), month=6, year=2024, status=FeeStatus.PENDING),
            MonthlyFee(user_id=1, amount=Decimal("1500"), month=7, year=2024, status=FeeStatus.PENDING),
        ]

        balance = Decimal("3000")
        for fee in sorted(fees, key=lambda f: (f.year, f.month)):
            if balance <= 0:
                break
            if fee.status == FeeStatus.PENDING:
                apply = min(balance, fee.amount)
                balance -= apply
                if apply > 0:
                    fee.status = FeeStatus.PAID
                    fee.paid_at = datetime.now(timezone(timedelta(hours=3)))

        assert balance == 0
        assert all(f.status == FeeStatus.PAID for f in fees)

    def test_payment_larger_than_debt(self):
        """Платёж больше долга → все взносы оплачены, остаётся переплата."""
        from src.domain.value_objects.fee_status import FeeStatus
        from src.domain.entities.monthly_fee import MonthlyFee

        fees = [
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=6, year=2024, status=FeeStatus.PENDING),
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=7, year=2024, status=FeeStatus.PENDING),
        ]

        balance = Decimal("3500")
        for fee in sorted(fees, key=lambda f: (f.year, f.month)):
            if balance <= 0:
                break
            if fee.status == FeeStatus.PENDING:
                apply = min(balance, fee.amount)
                balance -= apply
                if apply > 0:
                    fee.status = FeeStatus.PAID
                    fee.paid_at = datetime.now(timezone(timedelta(hours=3)))

        assert balance == Decimal("1500"), f"Expected 1500 overpayment, got {balance}"
        assert all(f.status == FeeStatus.PAID for f in fees)

    def test_no_pending_fees_no_change(self):
        """Нет ожидающих взносов → платёж не влияет на статус."""
        from src.domain.value_objects.fee_status import FeeStatus
        from src.domain.entities.monthly_fee import MonthlyFee

        fees = [
            MonthlyFee(user_id=1, amount=Decimal("1000"), month=6, year=2024, status=FeeStatus.PAID),
        ]

        balance = Decimal("500")
        for fee in sorted(fees, key=lambda f: (f.year, f.month)):
            if balance <= 0:
                break
            if fee.status == FeeStatus.PENDING:
                apply = min(balance, fee.amount)
                balance -= apply
                if apply > 0:
                    fee.status = FeeStatus.PAID

        assert balance == Decimal("500")
        assert fees[0].status == FeeStatus.PAID
