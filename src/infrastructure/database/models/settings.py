from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base


class ClubSettingsModel(Base):
    """Singleton table — хранит одну строку с настройками клуба."""

    __tablename__ = "club_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    club_name: Mapped[str] = mapped_column(String(100), default="Мотоклуб")
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1000.00"))
    payment_details: Mapped[str] = mapped_column(Text, default="Реквизиты не указаны")
    last_fee_assessment: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    treasury_adjustment: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
