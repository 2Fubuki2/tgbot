from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus


@dataclass
class User:
    id: int | None = None
    telegram_id: int = 0
    username: str | None = None
    full_name: str = ""
    role: UserRole = UserRole.MEMBER
    status: UserStatus = UserStatus.ACTIVE
    joined_at: datetime | None = None
    phone: str | None = None
    balance_credit: Decimal = Decimal(0)
    created_at: datetime | None = None
    updated_at: datetime | None = None
