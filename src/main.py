"""
TreasuryBot — Telegram bot for motorcycle club treasury management.

Entry point for polling mode (local development) and webhook mode (production).
"""

import asyncio
import logging
import os

from aiogram.utils.backoff import BackoffConfig
from sqlalchemy import inspect, text

from src.config.logger import setup_logging
from src.config.settings import settings
from src.infrastructure.database.base import Base
from src.infrastructure.database.session import engine, get_session
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.fee_repository import FeeRepository
from src.infrastructure.repositories.settings_repository import ClubSettingsRepository
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.domain.entities.monthly_fee import MonthlyFee
from src.domain.value_objects.fee_status import FeeStatus
from src.domain.entities.audit_log import AuditLog
from src.infrastructure.timezone import now_msk
from src.presentation.utils import safe_edit
from src.presentation.bot import create_bot, create_dispatcher

logger = logging.getLogger(__name__)

# Увеличенный backoff: конфликт Telegram требует ожидания >30s (timeout getUpdates)
_POLLING_BACKOFF = BackoffConfig(min_delay=5.0, max_delay=45.0, factor=1.5, jitter=0.2)


def _ensure_missing_columns(bind) -> None:
    """Backfill new SQLite columns for users with existing databases."""
    inspector = inspect(bind)
    table_columns = {
        "fines": {
            "paid_amount": "NUMERIC(10, 2) NOT NULL DEFAULT 0.00",
        },
        "payments": {
            "payment_type": "VARCHAR(20) NOT NULL DEFAULT 'fee'",
        },
    }
    for table_name, columns in table_columns.items():
        if table_name not in inspector.get_table_names():
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, ddl in columns.items():
            if column_name not in existing:
                bind.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl}'))


async def on_startup() -> None:
    """Actions to perform on bot startup."""
    logger.info("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_missing_columns)
    logger.info("Database tables created successfully.")


async def _daily_fee_assessment_task(bot) -> None:
    """Background task: check daily if fee assessment day has arrived."""
    from datetime import datetime, timedelta
    while True:
        await asyncio.sleep(60)  # check every minute near midnight
        now = now_msk()
        # Only act between 00:00 and 00:10 MSK to avoid double-triggering
        if now.hour != 0 or now.minute > 10:
            continue

        async for session in get_session():
            settings_repo = ClubSettingsRepository(session)
            fee_repo = FeeRepository(session)
            user_repo = UserRepository(session)
            audit_repo = AuditLogRepository(session)

            try:
                day = await settings_repo.get_fee_assessment_day()
            except Exception:
                break

            if day != now.day:
                break

            # Check if already assessed this month
            try:
                existing = await fee_repo.list_by_month(now.month, now.year)
                if existing:
                    logger.info("Daily scheduler: fees already assessed for %02d/%d, skipping", now.month, now.year)
                    break
            except Exception:
                break

            try:
                monthly_fee = await settings_repo.get_monthly_fee()
                members = await user_repo.list_active()
                assessed = 0
                for member in members:
                    if not await fee_repo.get_by_user_month(member.id, now.month, now.year):
                        fee = MonthlyFee(
                            user_id=int(member.id) if member.id else 0,
                            amount=monthly_fee,
                            month=now.month,
                            year=now.year,
                            status=FeeStatus.PENDING,
                        )
                        await fee_repo.create(fee)
                        assessed += 1

                await settings_repo.update(last_fee_assessment=datetime(now.year, now.month, 1))

                # Audit
                await audit_repo.create(AuditLog(
                    user_id=0,
                    action="assess_fees",
                    entity_type="monthly_fee",
                    details={"count": assessed, "month": now.month, "year": now.year, "amount": str(monthly_fee), "source": "daily_scheduler"},
                ))

                # Notify members
                for member in members:
                    try:
                        await bot.send_message(
                            member.telegram_id,
                            f"💰 <b>Начислен взнос</b>\n\n"
                            f"📅 За: {now.month:02d}/{now.year}\n"
                            f"💵 Сумма: <b>{monthly_fee:,.2f}₽</b>\n\n"
                            f"Оплатить можно через меню 💰 Мой бюджет → 📤 Я оплатил",
                        )
                    except Exception:
                        logger.exception("Scheduler: failed to notify %s", member.telegram_id)

                logger.info("Daily scheduler: assessed %d members for %02d/%d", assessed, now.month, now.year)
                break
            except Exception:
                break


async def _setup_webhook(bot) -> str | None:
    """Configure webhook if running on Railway/production. Returns webhook URL or None."""
    # Try to get webhook domain from env or settings
    domain = settings.webhook_domain or os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    if not domain:
        logger.info("No webhook domain configured, using polling mode")
        return None

    webhook_url = f"https://{domain}{settings.webhook_path}"
    try:
        result = await bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"],
        )
        if result:
            logger.info("Webhook set: %s", webhook_url)
            return webhook_url
        else:
            logger.warning("Failed to set webhook, falling back to polling")
            return None
    except Exception as e:
        logger.warning("Webhook setup failed: %s, using polling", e)
        return None


async def main() -> None:
    """Start the bot in polling or webhook mode."""
    setup_logging()
    logger.info("Starting TreasuryBot...")

    await on_startup()

    bot = create_bot()
    dp = create_dispatcher()

    # Try webhook mode first, fall back to polling
    webhook_url = await _setup_webhook(bot)

    if webhook_url:
        logger.info("Running in webhook mode: %s", webhook_url)
        # Import webhook app and run it
        from src.webhook_app import app as webhook_app

        import uvicorn

        uvicorn.run(webhook_app, host="0.0.0.0", port=8000, log_level="info")
    else:
        # Polling mode
        scheduler_task = asyncio.create_task(_daily_fee_assessment_task(bot))
        logger.info("Daily fee assessment scheduler started")

        try:
            await dp.start_polling(bot, backoff_config=_POLLING_BACKOFF)
        finally:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
            await bot.session.close()
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
