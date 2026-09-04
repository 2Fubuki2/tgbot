from __future__ import annotations

from decimal import Decimal

from sqlalchemy import cast, delete, func, or_, select, String, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.domain.interfaces.repositories import IUserRepository
from src.domain.value_objects.fee_status import FeeStatus
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.models.fine import FineModel
from src.infrastructure.database.models.monthly_fee import MonthlyFeeModel
from src.infrastructure.database.models.user import UserModel


class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            telegram_id=model.telegram_id,
            username=model.username,
            full_name=model.full_name,
            role=UserRole(model.role) if hasattr(model, 'role') and model.role is not None else UserRole.MEMBER,
            status=UserStatus(model.status) if hasattr(model, 'status') and model.status is not None else UserStatus.ACTIVE,
            joined_at=model.__dict__.get('joined_at'),
            phone=model.__dict__.get('phone'),
            balance_credit=model.__dict__.get('balance_credit') if 'balance_credit' in model.__dict__ else Decimal(0),
            created_at=model.__dict__.get('created_at'),
            updated_at=model.__dict__.get('updated_at'),
        )

    @staticmethod
    def _to_model(entity: User) -> UserModel:
        return UserModel(
            id=entity.id,
            telegram_id=entity.telegram_id,
            username=entity.username,
            full_name=entity.full_name,
            role=entity.role.value if entity.role else UserRole.MEMBER.value,
            status=entity.status.value if entity.status else UserStatus.ACTIVE.value,
            joined_at=entity.joined_at,
            phone=entity.phone,
            balance_credit=entity.balance_credit,
        )

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(UserModel).where(UserModel.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_id(self, user_id: int) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(self, user: User) -> User:
        model = self._to_model(user)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def update(self, user: User) -> User:
        stmt = select(UserModel).where(UserModel.id == user.id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"User with id {user.id} not found")

        model.telegram_id = user.telegram_id
        model.username = user.username
        model.full_name = user.full_name
        model.role = user.role.value if user.role else model.role
        model.status = user.status.value if user.status else model.status
        model.phone = user.phone
        model.balance_credit = user.balance_credit
        await self.session.flush()
        return self._to_domain(model)

    async def list_by_role(self, role: UserRole) -> list[User]:
        stmt = select(UserModel).where(UserModel.role == role.value).order_by(UserModel.full_name)
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_active(self) -> list[User]:
        stmt = (
            select(UserModel)
            .where(UserModel.status == UserStatus.ACTIVE.value)
            .order_by(UserModel.full_name)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_all(self) -> list[User]:
        stmt = select(UserModel).order_by(UserModel.full_name)
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def search(self, query: str) -> list[User]:
        pattern = f"%{query}%"
        stmt = select(UserModel).where(
            or_(
                UserModel.full_name.ilike(pattern),
                UserModel.username.ilike(pattern),
                cast(UserModel.telegram_id, String).ilike(pattern),
            )
        ).order_by(UserModel.full_name)
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def delete(self, user_id: int) -> None:
        """Soft-delete a user: expel and lock access to the bot."""
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            model.status = UserStatus.EXPELLED.value
            model.role = UserRole.MEMBER.value
            await self.session.flush()

    async def hard_delete(self, user_id: int) -> None:
        """Physically remove user row and all associated personal data from database."""
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return

        username = (model.username or "").lower()

        # Import dependent models for cascade cleanup
        from src.infrastructure.database.models.audit_log import AuditLogModel
        from src.infrastructure.database.models.expense import ExpenseModel
        from src.infrastructure.database.models.payment import PaymentModel
        from src.infrastructure.database.models.whitelist import WhitelistModel

        # Find a fallback user ID for actor references that are NOT NULL (e.g. issued_by, created_by)
        fallback_stmt = select(UserModel.id).where(UserModel.id != user_id).limit(1)
        fallback_res = await self.session.execute(fallback_stmt)
        fallback_id = fallback_res.scalar_one_or_none()

        # 1. Delete user's fines
        await self.session.execute(delete(FineModel).where(FineModel.user_id == user_id))
        # Detach fines issued or cancelled by this user
        if fallback_id is not None:
            await self.session.execute(
                update(FineModel).where(FineModel.issued_by == user_id).values(issued_by=fallback_id)
            )
        await self.session.execute(
            update(FineModel).where(FineModel.cancelled_by == user_id).values(cancelled_by=None)
        )

        # 2. Delete user's monthly fees
        await self.session.execute(delete(MonthlyFeeModel).where(MonthlyFeeModel.user_id == user_id))

        # 3. Delete user's payments
        await self.session.execute(delete(PaymentModel).where(PaymentModel.user_id == user_id))
        # Detach payments confirmed by this user
        await self.session.execute(
            update(PaymentModel).where(PaymentModel.confirmed_by == user_id).values(confirmed_by=None)
        )

        # 4. Detach expenses created by this user
        if fallback_id is not None:
            await self.session.execute(
                update(ExpenseModel).where(ExpenseModel.created_by == user_id).values(created_by=fallback_id)
            )

        # 5. Delete audit logs associated with this user
        await self.session.execute(delete(AuditLogModel).where(AuditLogModel.user_id == user_id))

        # 6. Delete whitelist invite for this user's username if any
        if username:
            await self.session.execute(
                delete(WhitelistModel).where(func.lower(WhitelistModel.username) == username)
            )

        # 7. Physically delete the user record
        await self.session.delete(model)
        await self.session.flush()

    async def count_active(self) -> int:
        stmt = select(func.count(UserModel.id)).where(UserModel.status == UserStatus.ACTIVE.value)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_debtors(self) -> int:
        """Count users with any outstanding fees (including partial) or active fines."""
        subq = (
            select(MonthlyFeeModel.user_id)
            .where(
                MonthlyFeeModel.status == FeeStatus.PENDING.value,
                MonthlyFeeModel.amount > MonthlyFeeModel.paid_amount,
            )
            .union(
                select(FineModel.user_id).where(FineModel.status == FineStatus.ACTIVE.value)
            )
            .subquery()
        )
        stmt = select(func.count()).select_from(subq)
        result = await self.session.execute(stmt)
        return result.scalar() or 0
