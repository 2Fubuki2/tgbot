from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.value_objects.expense_category import ExpenseCategory
from src.infrastructure.database.base import Base


class ExpenseModel(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(30), default=ExpenseCategory.OTHER)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    created_by_user = relationship("UserModel", back_populates="expenses")
