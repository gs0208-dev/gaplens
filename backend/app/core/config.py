from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. The only place that reads environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://gaplens:change-me-local-only@localhost:5432/gaplens"
    cors_origins: list[str] = ["http://localhost:5173"]

    # No default on purpose: the app must not start with a guessable signing key.
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_issuer: str = "gaplens-api"
    jwt_audience: str = "gaplens-web"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # Upload caps from docs/security.md. The text cap is also what keeps a whole document
    # inside a single LLM call (docs/ai-engineering.md).
    upload_max_bytes: int = 5 * 1024 * 1024
    upload_max_pages: int = 100
    upload_max_text_chars: int = 300_000

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
