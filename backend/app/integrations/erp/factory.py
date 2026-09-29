from app.core.config import get_settings
from app.core.errors import ErpDisabled
from app.integrations.erp.reader import ErpReader
from app.integrations.erp.sqlserver import SqlServerErpReader


def get_erp_reader() -> ErpReader:
    """FastAPI dependency. The real ERP is only reachable when ERP_ENABLED=true and fully configured."""
    settings = get_settings()
    if not settings.erp_enabled:
        raise ErpDisabled("ERP integration is disabled. Set ERP_ENABLED=true with read-only credentials to use it.")
    return SqlServerErpReader(settings)
