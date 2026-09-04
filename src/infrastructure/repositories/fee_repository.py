from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.monthly_fee import MonthlyFee
from src.domain.interfaces.repositories import IFeeRepository
from src.domain.value_objects.fee_status import FeeStatus
from src.infrastructure.database.models.monthly_fee import MonthlyFeeModel


class FeeRepository(IFeeRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_domain(model: MonthlyFeeModel) -> MonthlyFee:
        return MonthlyFee(
            id=model.id,
            user_id=model.user_id,
            amount=model.__dict__.get('amount'),
            paid_amount=model.__dict__.get('paid_amount', Decimal(0)),
            month=model.__dict__.get('month'),
            year=model.__dict__.get('year'),
            status=FeeStatus(model.__dict__.get('status')) if model.__dict__.get('status') is not None else FeeStatus.PENDING,
            comment=model.__dict__.get('comment'),
            assessed_at=model.__dict__.get('assessed_at'),
            paid_at=model.__dict__.get('paid_at'),
        )

    @staticmethod
    def _to_model(entity: MonthlyFee) -> MonthlyFeeModel:
        return MonthlyFeeModel(
            id=entity.id,
            user_id=entity.user_id,
            amount=entity.amount,
            paid_amount=entity.paid_amount,
            month=entity.month,
            year=entity.year,
            status=entity.status.value if entity.status else FeeStatus.PENDING.value,
            comment=entity.comment,
            paid_at=entity.paid_at,
        )

    async def get_by_id(self, fee_id: int) -> MonthlyFee | None:
        stmt = select(MonthlyFeeModel).where(MonthlyFeeModel.id == fee_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_user_month(self, user_id: int, month: int, year: int) -> MonthlyFee | None:
        stmt = select(MonthlyFeeModel).where(
            MonthlyFeeModel.user_id == user_id,
            MonthlyFeeModel.month == month,
            MonthlyFeeModel.year == year,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(self, fee: MonthlyFee) -> MonthlyFee:
        model = self._to_model(fee)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def update(self, fee: MonthlyFee) -> MonthlyFee:
        stmt = select(MonthlyFeeModel).where(MonthlyFeeModel.id == fee.id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"MonthlyFee with id {fee.id} not found")

        model.amount = fee.amount
        model.paid_amount = fee.paid_amount
        model.status = fee.status.value if fee.status else model.status
        model.comment = fee.comment
        model.paid_at = fee.paid_at
        await self.session.flush()
        return self._to_domain(model)

    async def list_by_user(self, user_id: int) -> list[MonthlyFee]:
        stmt = (
            select(MonthlyFeeModel)
            .where(MonthlyFeeModel.user_id == user_id)
            .order_by(MonthlyFeeModel.year.desc(), MonthlyFeeModel.month.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_pending_by_user(self, user_id: int) -> list[MonthlyFee]:
        stmt = (
            select(MonthlyFeeModel)
            .where(MonthlyFeeModel.user_id == user_id, MonthlyFeeModel.status == FeeStatus.PENDING.value)
            .order_by(MonthlyFeeModel.year, MonthlyFeeModel.month)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_month(self, month: int, year: int) -> list[MonthlyFee]:
        stmt = select(MonthlyFeeModel).where(
            MonthlyFeeModel.month == month, MonthlyFeeModel.year == year
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_all_pending(self) -> list[MonthlyFee]:
        stmt = select(MonthlyFeeModel).where(MonthlyFeeModel.status == FeeStatus.PENDING.value)
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def total_pending_amount(self) -> Decimal:
        stmt = select(func.coalesce(func.sum(MonthlyFeeModel.amount - MonthlyFeeModel.paid_amount), 0)).where(
            MonthlyFeeModel.status == FeeStatus.PENDING.value,
            MonthlyFeeModel.amount > MonthlyFeeModel.paid_amount,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or Decimal(0)

    async def delete(self, fee_id: int) -> None:
        await self.session.execute(delete(MonthlyFeeModel).where(MonthlyFeeModel.id == fee_id))
        await self.session.flush()

    async def get_last_assessment(self) -> tuple[int, int] | None:
        stmt = (
            select(MonthlyFeeModel.year, MonthlyFeeModel.month)
            .order_by(MonthlyFeeModel.year.desc(), MonthlyFeeModel.month.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        return (row.year, row.month) if row else None
