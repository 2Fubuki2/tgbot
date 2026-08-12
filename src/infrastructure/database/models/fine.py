from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.value_objects.fine_status import FineStatus
from src.infrastructure.database.base import Base


class FineModel(Base):
    __tablename__ = "fines"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=FineStatus.ACTIVE)
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user = relationship("UserModel", back_populates="fines", foreign_keys=[user_id])
    issuer = relationship("UserModel", foreign_keys=[issued_by])
