from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.value_objects.fee_status import FeeStatus
from src.infrastructure.database.base import Base


class MonthlyFeeModel(Base):
    __tablename__ = "monthly_fees"
    __table_args__ = (
        UniqueConstraint("user_id", "month", "year", name="uq_user_month_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=FeeStatus.PENDING)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("UserModel", back_populates="fees")
