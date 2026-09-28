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


@lru_cache
def get_settings() -> Settings:
    return Settings()
