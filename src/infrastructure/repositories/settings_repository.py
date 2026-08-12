from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.interfaces.repositories import IClubSettingsRepository
from src.infrastructure.database.models.settings import ClubSettingsModel


class ClubSettingsRepository(IClubSettingsRepository):
    """Settings repository — гарантирует, что в таблице всегда есть строка."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _ensure_row(self) -> ClubSettingsModel:
        """Create default row if doesn't exist (singleton pattern)."""
        stmt = select(ClubSettingsModel).limit(1)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            model = ClubSettingsModel(id=1)
            self.session.add(model)
            await self.session.flush()
        return model

    async def get(self) -> dict:
        model = await self._ensure_row()
        return {
            "club_name": model.club_name,
            "monthly_fee": model.monthly_fee,
            "payment_details": model.payment_details,
            "last_fee_assessment": model.last_fee_assessment,
        }

    async def update(self, **kwargs) -> dict:
        model = await self._ensure_row()
        allowed = {"club_name", "monthly_fee", "payment_details", "last_fee_assessment"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(model, key, value)
        await self.session.flush()
        return await self.get()

    async def get_monthly_fee(self) -> Decimal:
        model = await self._ensure_row()
        return model.monthly_fee

    async def get_payment_details(self) -> str:
        model = await self._ensure_row()
        return model.payment_details
