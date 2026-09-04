from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.audit_log import AuditLog
from src.domain.interfaces.repositories import IAuditLogRepository
from src.infrastructure.database.models.audit_log import AuditLogModel


class AuditLogRepository(IAuditLogRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_domain(model: AuditLogModel) -> AuditLog:
        return AuditLog(
            id=model.id,
            user_id=model.user_id,
            action=model.__dict__.get('action'),
            entity_type=model.__dict__.get('entity_type'),
            entity_id=model.__dict__.get('entity_id'),
            details=json.loads(model.__dict__.get('details')) if model.__dict__.get('details') else None,
            created_at=model.__dict__.get('created_at'),
        )

    @staticmethod
    def _to_model(entity: AuditLog) -> AuditLogModel:
        return AuditLogModel(
            id=entity.id,
            user_id=entity.user_id,
            action=entity.action,
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            details=json.dumps(entity.details, ensure_ascii=False, default=str) if entity.details else None,
        )

    async def create(self, log: AuditLog) -> AuditLog:
        model = self._to_model(log)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def list_all(self, limit: int = 100) -> list[AuditLog]:
        stmt = select(AuditLogModel).order_by(AuditLogModel.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_paginated(self, page: int = 0, per_page: int = 10) -> tuple[list[AuditLog], int]:
        """Returns (logs_page, total_count)."""
        # Total count
        count_stmt = select(func.count(AuditLogModel.id))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        stmt = (
            select(AuditLogModel)
            .order_by(AuditLogModel.created_at.desc())
            .offset(page * per_page)
            .limit(per_page)
        )
        result = await self.session.execute(stmt)
        logs = [self._to_domain(m) for m in result.scalars().all()]
        return logs, total

    async def list_by_user(self, user_id: int, limit: int = 50) -> list[AuditLog]:
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.user_id == user_id)
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]
