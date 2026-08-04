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
    # 維運通報（排程失敗等）的去處。沒設定時 core.alerts 會退回下面兩支判讀
    # 用的 webhook —— 跟判讀混頻道也好過完全沒聲音。
    discord_ops_webhook_url: SecretStr | None = None
    log_level: str = "INFO"
    cors_origins: list[str] = ["https://stock.paul-learning.dev"]

    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_endpoint_url: str | None = None
    r2_bucket: str | None = None

    # Discord webhook for 盤中大盤冷熱判讀. Falls back to
    # ``discord_stock_webhook_url`` so no new secret is required.
    discord_market_webhook_url: SecretStr | None = None


settings = Settings()
