from abc import ABC, abstractmethod
from decimal import Decimal

from src.domain.entities.audit_log import AuditLog
from src.domain.entities.expense import Expense
from src.domain.entities.fine import Fine
from src.domain.entities.monthly_fee import MonthlyFee
from src.domain.entities.payment import Payment
from src.domain.entities.user import User
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus


class IUserRepository(ABC):
    @abstractmethod
    async def get_by_telegram_id(self, telegram_id: int) -> User | None: ...

    @abstractmethod
    async def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    async def create(self, user: User) -> User: ...

    @abstractmethod
    async def update(self, user: User) -> User: ...

    @abstractmethod
    async def list_by_role(self, role: UserRole) -> list[User]: ...

    @abstractmethod
    async def list_active(self) -> list[User]: ...

    @abstractmethod
    async def list_all(self) -> list[User]: ...

    @abstractmethod
    async def search(self, query: str) -> list[User]: ...

    @abstractmethod
    async def count_active(self) -> int: ...

    @abstractmethod
    async def count_debtors(self) -> int: ...


class IPaymentRepository(ABC):
    @abstractmethod
    async def get_by_id(self, payment_id: int) -> Payment | None: ...

    @abstractmethod
    async def create(self, payment: Payment) -> Payment: ...

    @abstractmethod
    async def update(self, payment: Payment) -> Payment: ...

    @abstractmethod
    async def list_by_user(self, user_id: int) -> list[Payment]: ...

    @abstractmethod
    async def list_pending(self) -> list[Payment]: ...

    @abstractmethod
    async def list_confirmed(self) -> list[Payment]: ...

    @abstractmethod
    async def list_by_month(self, month: int, year: int) -> list[Payment]: ...

    @abstractmethod
    async def delete(self, payment_id: int) -> None: ...

    @abstractmethod
    async def total_confirmed_amount(self) -> Decimal: ...

    @abstractmethod
    async def count_pending(self) -> int: ...


class IFeeRepository(ABC):
    @abstractmethod
    async def get_by_id(self, fee_id: int) -> MonthlyFee | None: ...

    @abstractmethod
    async def get_by_user_month(self, user_id: int, month: int, year: int) -> MonthlyFee | None: ...

    @abstractmethod
    async def create(self, fee: MonthlyFee) -> MonthlyFee: ...

    @abstractmethod
    async def update(self, fee: MonthlyFee) -> MonthlyFee: ...

    @abstractmethod
    async def list_by_user(self, user_id: int) -> list[MonthlyFee]: ...

    @abstractmethod
    async def list_pending_by_user(self, user_id: int) -> list[MonthlyFee]: ...

    @abstractmethod
    async def list_by_month(self, month: int, year: int) -> list[MonthlyFee]: ...

    @abstractmethod
    async def list_all_pending(self) -> list[MonthlyFee]: ...

    @abstractmethod
    async def total_pending_amount(self) -> Decimal: ...

    @abstractmethod
    async def get_last_assessment(self) -> tuple[int, int] | None: ...

    @abstractmethod
    async def delete(self, fee_id: int) -> None: ...


class IFineRepository(ABC):
    @abstractmethod
    async def get_by_id(self, fine_id: int) -> Fine | None: ...

    @abstractmethod
    async def create(self, fine: Fine) -> Fine: ...

    @abstractmethod
    async def update(self, fine: Fine) -> Fine: ...

    @abstractmethod
    async def list_by_user(self, user_id: int) -> list[Fine]: ...

    @abstractmethod
    async def list_active_by_user(self, user_id: int) -> list[Fine]: ...

    @abstractmethod
    async def list_active(self) -> list[Fine]: ...

    @abstractmethod
    async def total_active_amount(self) -> Decimal: ...

    @abstractmethod
    async def delete(self, fine_id: int) -> None: ...


class IExpenseRepository(ABC):
    @abstractmethod
    async def get_by_id(self, expense_id: int) -> Expense | None: ...

    @abstractmethod
    async def create(self, expense: Expense) -> Expense: ...

    @abstractmethod
    async def update(self, expense: Expense) -> Expense: ...

    @abstractmethod
    async def delete(self, expense_id: int) -> None: ...

    @abstractmethod
    async def list_all(self) -> list[Expense]: ...

    @abstractmethod
    async def list_by_date_range(self, start: str, end: str) -> list[Expense]: ...

    @abstractmethod
    async def total_amount(self) -> Decimal: ...


class IAuditLogRepository(ABC):
    @abstractmethod
    async def create(self, log: AuditLog) -> AuditLog: ...

    @abstractmethod
    async def list_all(self, limit: int = 100) -> list[AuditLog]: ...

    @abstractmethod
    async def list_paginated(self, page: int = 0, per_page: int = 10) -> tuple[list[AuditLog], int]: ...

    @abstractmethod
    async def list_by_user(self, user_id: int, limit: int = 50) -> list[AuditLog]: ...


class IClubSettingsRepository(ABC):
    @abstractmethod
    async def get(self) -> dict: ...

    @abstractmethod
    async def update(self, **kwargs) -> dict: ...

    @abstractmethod
    async def get_monthly_fee(self) -> Decimal: ...

    @abstractmethod
    async def get_payment_details(self) -> str: ...

    @abstractmethod
    async def get_treasury_adjustment(self) -> Decimal: ...

    @abstractmethod
    async def set_treasury_adjustment(self, value: Decimal) -> Decimal: ...
