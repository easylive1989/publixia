"""Centralised configuration. Read once at import; no scattered os.environ.get."""
import os
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: str = os.path.join(
        os.path.dirname(__file__), "..", "stock_dashboard.db"
    )
    discord_stock_webhook_url: SecretStr | None = None
    discord_ops_webhook_url: SecretStr | None = None
    finmind_token: SecretStr = SecretStr("")
    log_level: str = "INFO"
    cors_origins: list[str] = ["https://paul-learning.dev"]


settings = Settings()
