from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.domain.value_objects.fee_status import FeeStatus


@dataclass
class MonthlyFee:
    id: int | None = None
    user_id: int = 0
    amount: Decimal = Decimal("0")
    month: int = 0
    year: int = 0
    status: FeeStatus = FeeStatus.PENDING
    assessed_at: datetime | None = None
    paid_at: datetime | None = None
