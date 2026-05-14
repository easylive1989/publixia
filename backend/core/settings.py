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
    cors_origins: list[str] = ["https://stock.paul-learning.dev"]

    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_endpoint_url: str | None = None
    r2_bucket: str | None = None

    # Shared secret + URL for the Cloudflare Worker that produces the
    # daily 外資動向 AI report. Worker → FastAPI auth and the manual
    # regenerate path both check this token.
    foreign_flow_worker_token: SecretStr | None = None
    foreign_flow_worker_url:   str        | None = None


settings = Settings()
