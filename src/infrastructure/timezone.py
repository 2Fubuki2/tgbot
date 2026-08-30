"""Утилиты работы с московским временем (UTC+3, фиксированный сдвиг)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

_MSK = timezone(timedelta(hours=3))


def now_msk() -> datetime:
    """Текущие дата и время в московском времени."""
    return datetime.now(_MSK)


def today_msk() -> date:
    """Сегодняшняя дата в московском времени."""
    return now_msk().date()


def utcnow_to_msk(dt: datetime) -> datetime:
    """Конвертировать UTC-время в MSK."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_MSK)
    return dt.astimezone(_MSK)
