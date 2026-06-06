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

    # Cloudflare Workers AI — used to extract buy/sell signals from posts.
    # Backend calls the REST API directly (no separate Worker).
    cf_account_id: str | None = None
    cf_api_token:  SecretStr | None = None
    cf_ai_model:   str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

    # Groq Whisper — free-tier speech-to-text for podcast episodes.
    groq_api_key:  SecretStr | None = None
    groq_stt_model: str = "whisper-large-v3"

    # Discord webhook for new-trade notifications.
    discord_copytrade_webhook_url: SecretStr | None = None


settings = Settings()
