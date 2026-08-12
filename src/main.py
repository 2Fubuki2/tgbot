"""
TreasuryBot — Telegram bot for motorcycle club treasury management.

Entry point for polling mode (local development).
"""

import asyncio
import logging

from sqlalchemy import inspect, text

from src.config.logger import setup_logging
from src.infrastructure.database.base import Base
from src.infrastructure.database.session import engine
from src.presentation.bot import create_bot, create_dispatcher

logger = logging.getLogger(__name__)


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


async def main() -> None:
    """Start the bot in polling mode."""
    setup_logging()
    logger.info("Starting TreasuryBot...")

    await on_startup()

    bot = create_bot()
    dp = create_dispatcher()

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
