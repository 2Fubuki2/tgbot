import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone

from src.config.settings import settings


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured production logs (Railway-parseable)."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging() -> None:
    """Configure logging for the application.

    Production (Railway): JSON to stdout for log aggregation.
    Local dev: human-readable to stdout + rotating file log.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    use_json = settings.use_webhook or settings.webhook_domain

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    if use_json:
        # Production: JSON to stdout — Railway log aggregator parses it
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
    else:
        # Local dev: human-readable to stdout
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))

        # Also write to a rotating file (max 5MB, keep 3 backups)
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                "logs/app.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
            root_logger.addHandler(file_handler)
        except OSError:
            pass  # logs/ directory may not exist; skip file logging

    root_logger.addHandler(handler)

    # Suppress noisy libs
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)
    logging.getLogger("reportlab").setLevel(logging.WARNING)
