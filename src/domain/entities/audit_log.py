from dataclasses import dataclass
from datetime import datetime


@dataclass
class AuditLog:
    id: int | None = None
    user_id: int = 0
    action: str = ""
    entity_type: str = ""
    entity_id: int | None = None
    details: dict | None = None
    created_at: datetime | None = None
