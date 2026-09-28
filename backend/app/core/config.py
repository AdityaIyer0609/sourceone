from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SourceOne B2B Platform API"
    app_version: str = "0.1.0"

    database_url: SecretStr
    database_echo: bool = False

    # Business day boundaries (IST has no DST, so a fixed offset is exact).
    business_utc_offset_minutes: int = 330

    pricing_history_min_points: int = 2
    pricing_volatility_min_points: int = 5
    pricing_negotiation_window_days: int = 30

    # Header-based identity for local demos only; never enable in a shared environment.
    demo_auth_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
