from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.domain.value_objects.payment_status import PaymentStatus


@dataclass
class Payment:
    id: int | None = None
    user_id: int = 0
    amount: Decimal = Decimal("0")
    payment_date: date | None = None
    month: int = 0
    year: int = 0
    payment_type: str = "fee"
    payment_method: str | None = None
    comment: str | None = None
    receipt_photo_id: str | None = None
    status: PaymentStatus = PaymentStatus.PENDING
    confirmed_by: int | None = None
    confirmed_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
