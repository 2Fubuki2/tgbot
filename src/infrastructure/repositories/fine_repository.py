from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.fine import Fine
from src.domain.interfaces.repositories import IFineRepository
from src.domain.value_objects.fine_status import FineStatus
from src.infrastructure.database.models.fine import FineModel


class FineRepository(IFineRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_domain(model: FineModel) -> Fine:
        return Fine(
            id=model.id,
            user_id=model.user_id,
            amount=model.__dict__.get('amount'),
            paid_amount=model.__dict__.get('paid_amount', Decimal(0)),
            reason=model.__dict__.get('reason'),
            comment=model.__dict__.get('comment'),
            issued_by=model.__dict__.get('issued_by'),
            status=FineStatus(model.__dict__.get('status')) if model.__dict__.get('status') is not None else FineStatus.ACTIVE,
            cancelled_by=model.__dict__.get('cancelled_by'),
            cancelled_at=model.__dict__.get('cancelled_at'),
            created_at=model.__dict__.get('created_at'),
            updated_at=model.__dict__.get('updated_at'),
        )

    @staticmethod
    def _to_model(entity: Fine) -> FineModel:
        return FineModel(
            id=entity.id,
            user_id=entity.user_id,
            amount=entity.amount,
            paid_amount=entity.paid_amount,
            reason=entity.reason,
            comment=entity.comment,
            issued_by=entity.issued_by,
            status=entity.status.value if entity.status else FineStatus.ACTIVE.value,
            cancelled_by=entity.cancelled_by,
            cancelled_at=entity.cancelled_at,
        )

    async def get_by_id(self, fine_id: int) -> Fine | None:
        stmt = select(FineModel).where(FineModel.id == fine_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(self, fine: Fine) -> Fine:
        model = self._to_model(fine)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def update(self, fine: Fine) -> Fine:
        stmt = select(FineModel).where(FineModel.id == fine.id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Fine with id {fine.id} not found")

        model.amount = fine.amount
        model.paid_amount = fine.paid_amount
        model.status = fine.status.value if fine.status else model.status
        model.cancelled_by = fine.cancelled_by
        model.cancelled_at = fine.cancelled_at
        await self.session.flush()
        return self._to_domain(model)

    async def list_by_user(self, user_id: int) -> list[Fine]:
        stmt = (
            select(FineModel)
            .where(FineModel.user_id == user_id)
            .order_by(FineModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_active_by_user(self, user_id: int) -> list[Fine]:
        stmt = (
            select(FineModel)
            .where(
                FineModel.user_id == user_id,
                FineModel.status == FineStatus.ACTIVE.value,
                FineModel.paid_amount < FineModel.amount,
            )
            .order_by(FineModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_active(self) -> list[Fine]:
        stmt = (
            select(FineModel)
            .where(
                FineModel.status == FineStatus.ACTIVE.value,
                FineModel.paid_amount < FineModel.amount,
            )
            .order_by(FineModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def delete(self, fine_id: int) -> None:
        await self.session.execute(delete(FineModel).where(FineModel.id == fine_id))
        await self.session.flush()

    async def total_active_amount(self) -> Decimal:
        stmt = select(func.coalesce(func.sum(FineModel.amount - FineModel.paid_amount), 0)).where(
            FineModel.status == FineStatus.ACTIVE.value
        )
        result = await self.session.execute(stmt)
        return result.scalar() or Decimal(0)
