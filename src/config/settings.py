from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram
    bot_token: str
    proxy_url: str | None = None

    # Database
    database_url: str = "sqlite+aiosqlite:///./treasurybot.db"

    # Admin Telegram IDs (comma-separated in .env, parsed as list)
    admin_ids: list[int] = []

    # Logging
    log_level: str = "INFO"
    timezone: str = "Europe/Moscow"

    # Webhook settings для Railway/Render/PythonAnywhere
    webhook_domain: str = ""
    webhook_path: str = "/webhook"
    use_webhook: bool = False

    # Host и порт для webhook
    webapp_host: str = "0.0.0.0"
    webapp_port: int = 8000

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: str | list | None) -> list[int]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Split by comma or newline, strip whitespace
            parts = [p.strip() for p in v.replace("\n", ",").split(",") if p.strip()]
            result = []
            for p in parts:
                try:
                    result.append(int(p))
                except ValueError:
                    pass
            return result
        try:
            return [int(v)]
        except (ValueError, TypeError):
            return []


settings = Settings()  # type: ignore[call-arg]
