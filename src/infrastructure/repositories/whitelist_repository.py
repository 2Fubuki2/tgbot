from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.whitelist import WhitelistEntry
from src.domain.interfaces.repositories import IWhitelistRepository
from src.domain.value_objects.role import UserRole
from src.infrastructure.database.models.whitelist import WhitelistModel
from src.infrastructure.timezone import now_msk


class WhitelistRepository(IWhitelistRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_domain(model: WhitelistModel) -> WhitelistEntry:
        return WhitelistEntry(
            id=model.id,
            username=model.username,
            full_name=model.full_name,
            role=UserRole(model.role),
            created_by=model.created_by,
            created_at=model.created_at,
            is_used=model.is_used,
            activated_at=model.activated_at,
        )

    async def get_by_username(self, username: str) -> WhitelistEntry | None:
        clean = username.lstrip("@").strip().lower()
        stmt = select(WhitelistModel).where(
            func.lower(WhitelistModel.username) == clean,
            WhitelistModel.is_used.is_(False),
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(self, entry: WhitelistEntry) -> WhitelistEntry:
        clean = entry.username.lstrip("@").strip().lower()
        model = WhitelistModel(
            username=clean,
            full_name=entry.full_name,
            role=entry.role.value if hasattr(entry.role, "value") else str(entry.role),
            created_by=entry.created_by,
            is_used=False,
            created_at=entry.created_at or now_msk(),
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def list_pending(self) -> list[WhitelistEntry]:
        stmt = (
            select(WhitelistModel)
            .where(WhitelistModel.is_used.is_(False))
            .order_by(WhitelistModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def mark_used(self, entry_id: int) -> None:
        stmt = select(WhitelistModel).where(WhitelistModel.id == entry_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            model.is_used = True
            model.activated_at = now_msk()
            await self.session.flush()

    async def delete(self, entry_id: int) -> None:
        stmt = delete(WhitelistModel).where(WhitelistModel.id == entry_id)
        await self.session.execute(stmt)
        await self.session.flush()
