from dataclasses import dataclass
from datetime import datetime

from src.domain.value_objects.role import UserRole


@dataclass
class WhitelistEntry:
    id: int | None
    username: str
    full_name: str
    role: UserRole
    created_by: int
    created_at: datetime
    is_used: bool = False
    activated_at: datetime | None = None
