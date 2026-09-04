from dataclasses import dataclass
from datetime import datetime

from src.domain.value_objects.role import UserRole


@dataclass
class WhitelistEntry:
    id: int | None = None
    username: str = ""
    full_name: str = ""
    role: UserRole = UserRole.MEMBER
    created_by: int = 0
    created_at: datetime | None = None
    is_used: bool = False
    activated_at: datetime | None = None
