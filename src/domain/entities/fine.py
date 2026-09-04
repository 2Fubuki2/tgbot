from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.domain.value_objects.fine_status import FineStatus


@dataclass
class Fine:
    id: int | None = None
    user_id: int = 0
    amount: Decimal = Decimal(0)
    paid_amount: Decimal = Decimal(0)
    reason: str = ""
    comment: str | None = None
    issued_by: int = 0
    status: FineStatus = FineStatus.ACTIVE
    cancelled_by: int | None = None
    cancelled_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def remaining_amount(self) -> Decimal:
        return max(self.amount - self.paid_amount, Decimal(0))
