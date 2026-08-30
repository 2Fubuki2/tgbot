from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.payment import Payment
from src.domain.interfaces.repositories import IPaymentRepository
from src.domain.value_objects.payment_status import PaymentStatus
from src.infrastructure.database.models.payment import PaymentModel


class PaymentRepository(IPaymentRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_domain(model: PaymentModel) -> Payment:
        return Payment(
            id=model.id,
            user_id=model.user_id,
            amount=model.__dict__.get('amount'),
            payment_date=model.__dict__.get('payment_date'),
            month=model.__dict__.get('month'),
            year=model.__dict__.get('year'),
            payment_type=model.__dict__.get('payment_type', 'fee'),
            payment_method=model.__dict__.get('payment_method'),
            comment=model.__dict__.get('comment'),
            receipt_photo_id=model.__dict__.get('receipt_photo_id'),
            status=PaymentStatus(model.__dict__.get('status')) if model.__dict__.get('status') is not None else PaymentStatus.PENDING,
            confirmed_by=model.__dict__.get('confirmed_by'),
            confirmed_at=model.__dict__.get('confirmed_at'),
            rejection_reason=model.__dict__.get('rejection_reason'),
            created_at=model.__dict__.get('created_at'),
            updated_at=model.__dict__.get('updated_at'),
        )

    @staticmethod
    def _to_model(entity: Payment) -> PaymentModel:
        return PaymentModel(
            id=entity.id,
            user_id=entity.user_id,
            amount=entity.amount,
            payment_date=entity.payment_date,
            month=entity.month,
            year=entity.year,
            payment_type=entity.payment_type or 'fee',
            payment_method=entity.payment_method,
            comment=entity.comment,
            receipt_photo_id=entity.receipt_photo_id,
            status=entity.status.value if entity.status else PaymentStatus.PENDING.value,
            confirmed_by=entity.confirmed_by,
            confirmed_at=entity.confirmed_at,
            rejection_reason=entity.rejection_reason,
        )

    async def get_by_id(self, payment_id: int) -> Payment | None:
        stmt = select(PaymentModel).where(PaymentModel.id == payment_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(self, payment: Payment) -> Payment:
        model = self._to_model(payment)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def update(self, payment: Payment) -> Payment:
        stmt = select(PaymentModel).where(PaymentModel.id == payment.id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Payment with id {payment.id} not found")

        model.amount = payment.amount
        model.payment_date = payment.payment_date
        model.month = payment.month
        model.year = payment.year
        model.payment_type = payment.payment_type or 'fee'
        model.payment_method = payment.payment_method
        model.comment = payment.comment
        model.receipt_photo_id = payment.receipt_photo_id
        model.status = payment.status.value if payment.status else model.status
        model.confirmed_by = payment.confirmed_by
        model.confirmed_at = payment.confirmed_at
        model.rejection_reason = payment.rejection_reason
        await self.session.flush()
        return self._to_domain(model)

    async def list_by_user(self, user_id: int) -> list[Payment]:
        stmt = select(PaymentModel).where(PaymentModel.user_id == user_id).order_by(PaymentModel.created_at.desc())
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_pending(self) -> list[Payment]:
        stmt = select(PaymentModel).where(PaymentModel.status == PaymentStatus.PENDING.value).order_by(PaymentModel.created_at)
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_confirmed(self) -> list[Payment]:
        stmt = select(PaymentModel).where(PaymentModel.status == PaymentStatus.CONFIRMED.value).order_by(PaymentModel.created_at.desc())
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_month(self, month: int, year: int) -> list[Payment]:
        stmt = (
            select(PaymentModel)
            .where(PaymentModel.month == month, PaymentModel.year == year)
            .order_by(PaymentModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def delete(self, payment_id: int) -> None:
        await self.session.execute(delete(PaymentModel).where(PaymentModel.id == payment_id))
        await self.session.flush()

    async def total_confirmed_amount(self) -> Decimal:
        stmt = select(func.coalesce(func.sum(PaymentModel.amount), 0)).where(
            PaymentModel.status == PaymentStatus.CONFIRMED.value
        )
        result = await self.session.execute(stmt)
        return result.scalar() or Decimal("0")

    async def count_pending(self) -> int:
        stmt = select(func.count(PaymentModel.id)).where(
            PaymentModel.status == PaymentStatus.PENDING.value
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
