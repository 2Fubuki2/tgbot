from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.base import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.MEMBER)
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.ACTIVE)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    balance_credit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    payments = relationship("PaymentModel", back_populates="user", foreign_keys="[PaymentModel.user_id]", lazy="selectin")
    fees = relationship("MonthlyFeeModel", back_populates="user", lazy="selectin")
    fines = relationship("FineModel", back_populates="user", foreign_keys="[FineModel.user_id]", lazy="selectin")
    expenses = relationship("ExpenseModel", back_populates="created_by_user", lazy="selectin")
    audit_logs = relationship("AuditLogModel", back_populates="user", lazy="selectin")
