from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.expense import Expense
from src.domain.interfaces.repositories import IExpenseRepository
from src.domain.value_objects.expense_category import ExpenseCategory
from src.infrastructure.database.models.expense import ExpenseModel


class ExpenseRepository(IExpenseRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_domain(model: ExpenseModel) -> Expense:
        return Expense(
            id=model.id,
            amount=model.__dict__.get('amount'),
            category=ExpenseCategory(model.__dict__.get('category')) if model.__dict__.get('category') is not None else ExpenseCategory.OTHER,
            comment=model.__dict__.get('comment'),
            created_by=model.__dict__.get('created_by'),
            expense_date=model.__dict__.get('expense_date'),
            created_at=model.__dict__.get('created_at'),
        )

    @staticmethod
    def _to_model(entity: Expense) -> ExpenseModel:
        return ExpenseModel(
            id=entity.id,
            amount=entity.amount,
            category=entity.category.value if entity.category else ExpenseCategory.OTHER.value,
            comment=entity.comment,
            created_by=entity.created_by,
            expense_date=entity.expense_date,
        )

    async def get_by_id(self, expense_id: int) -> Expense | None:
        stmt = select(ExpenseModel).where(ExpenseModel.id == expense_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(self, expense: Expense) -> Expense:
        model = self._to_model(expense)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def update(self, expense: Expense) -> Expense:
        stmt = select(ExpenseModel).where(ExpenseModel.id == expense.id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Expense with id {expense.id} not found")

        model.amount = expense.amount
        model.category = expense.category.value if expense.category else ExpenseCategory.OTHER.value
        model.comment = expense.comment
        model.created_by = expense.created_by
        model.expense_date = expense.expense_date
        await self.session.flush()
        return self._to_domain(model)

    async def delete(self, expense_id: int) -> None:
        await self.session.execute(delete(ExpenseModel).where(ExpenseModel.id == expense_id))
        await self.session.flush()

    async def list_all(self) -> list[Expense]:
        stmt = select(ExpenseModel).order_by(ExpenseModel.expense_date.desc())
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_date_range(self, start: str, end: str) -> list[Expense]:
        stmt = select(ExpenseModel).where(
            ExpenseModel.expense_date >= start, ExpenseModel.expense_date <= end
        ).order_by(ExpenseModel.expense_date.desc())
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def total_amount(self) -> Decimal:
        stmt = select(func.coalesce(func.sum(ExpenseModel.amount), 0))
        result = await self.session.execute(stmt)
        return result.scalar() or Decimal("0")
