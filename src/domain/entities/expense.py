from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.domain.value_objects.expense_category import ExpenseCategory


@dataclass
class Expense:
    id: int | None = None
    amount: Decimal = Decimal("0")
    category: ExpenseCategory = ExpenseCategory.OTHER
    comment: str | None = None
    created_by: int = 0
    expense_date: date | None = None
    created_at: datetime | None = None
