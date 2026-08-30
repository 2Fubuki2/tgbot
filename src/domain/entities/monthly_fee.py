from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.domain.value_objects.fee_status import FeeStatus


@dataclass
class MonthlyFee:
    id: int | None = None
    user_id: int = 0
    amount: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    month: int = 0
    year: int = 0
    status: FeeStatus = FeeStatus.PENDING
    comment: str | None = None
    assessed_at: datetime | None = None
    paid_at: datetime | None = None

    @property
    def remaining_amount(self) -> Decimal:
        return max(self.amount - self.paid_amount, Decimal("0"))
