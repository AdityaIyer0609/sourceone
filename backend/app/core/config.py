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

    # Buyers and suppliers do not see supplier names, negotiations, or other suppliers.
    # Platform and pricing admins still see every feature. Tests leave this off.
    # When true, buyers and suppliers do not see other suppliers. Admins still do.
    hide_suppliers: bool = False

    # Signs login tokens. Override outside local development.
    auth_secret: SecretStr = SecretStr("sourceone-dev-auth-secret")
    auth_token_ttl_seconds: int = 60 * 60 * 12

    # SourceOne product files. Not ERP documents.
    document_dir: Path = BACKEND_DIR / "var" / "product_documents"

    # ERP (SQL Server) is read-only for SourceOne. The connection stays off unless explicitly enabled
    # and fully configured; use a login that only has SELECT on the tables below.
    erp_enabled: bool = False
    erp_host: str | None = None
    erp_port: int = 1433
    erp_username: str | None = None
    erp_password: SecretStr | None = None
    erp_odbc_driver: str = "ODBC Driver 18 for SQL Server"
    erp_encrypt: bool = True
    erp_trust_server_certificate: bool = False
    erp_login_timeout_seconds: int = 15
    erp_query_timeout_seconds: int = 60
    erp_price_database: str = "MaterialProcessing"
    erp_customer_database: str = "Despatch"
    erp_rate_source_code: str = "ERP-DOMESTICPRICE1"

    # Road distance for freight fallback only. Never sent to the browser.
    geoapify_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
