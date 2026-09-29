"""Read-only SQL Server reader for the ERP.

Safety layers, all of which must hold:
- the ERP login should only have SELECT rights (configured on the ERP side);
- the connection asks for read-only access (ApplicationIntent=ReadOnly, ODBC read-only mode);
- only the fixed SELECT statements below are ever executed, each checked by `assert_read_only`;
- every connection is rolled back and closed, never committed.
"""

import re
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from types import ModuleType
from typing import Any

from app.core.config import Settings
from app.core.errors import ErpNotConfigured, ErpUnavailable
from app.integrations.erp.constants import CUSTOMER_COLUMNS, GRADE_COLUMNS, PRICE_COLUMNS
from app.integrations.erp.reader import ErpRow

# Latest price date = every row on the calendar day of MAX(SysDate); a price date is a full re-entry.
PRICE_SNAPSHOT_SQL = (
    "SELECT p.SrNo, p.SysDate, p.Company, p.Quality, p.Grade, p.Location, p.Sector, p.Appilcation, "
    "p.Currency, p.CurrencyCon, p.UnitPrice, p.Basic, p.Total, p.GrandTotal, p.CashDis, p.LocDis, p.Trade, "
    "p.Special, p.QD, p.AQD, p.MOU, p.Frieght, p.GSTPER, p.GSTAMT, p.QtySlab "
    "FROM dbo.DomesticPrice1 AS p "
    "WHERE p.SysDate >= CAST((SELECT MAX(m.SysDate) FROM dbo.DomesticPrice1 AS m) AS date)"
)
# DomesticGrade names the producer CompanyName (DomesticPrice1 calls the same thing Company) and
# stores the item link as itemcode. Aliases keep the reader contract stable.
GRADES_SQL = (
    "SELECT g.SrNo AS SrNo, g.CompanyName AS Company, g.Quality AS Quality, g.Grade AS Grade, "
    "g.MFI AS MFI, g.Density AS Density, g.itemcode AS ItemCode "
    "FROM dbo.DomesticGrade AS g"
)
CUSTOMERS_SQL = (
    "SELECT c.CompanyName AS CompanyName, c.NewGSTNo AS GSTIN, c.PINCode AS PINCode "
    "FROM dbo.CompanyMaster AS c"
)
STATEMENTS = (PRICE_SNAPSHOT_SQL, GRADES_SQL, CUSTOMERS_SQL)

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|CALL|GRANT|REVOKE|DENY|"
    r"BACKUP|RESTORE|INTO|OPENROWSET|OPENQUERY|OPENDATASOURCE|DBCC|KILL|SHUTDOWN|RECONFIGURE|USE|SET|"
    r"BEGIN|COMMIT|WAITFOR|DECLARE|SP_\w+|XP_\w+)\b",
    re.IGNORECASE,
)


def assert_read_only(sql: str) -> str:
    """Only a single plain SELECT is allowed; anything that could change ERP state is refused."""
    statement = sql.strip()
    if not re.match(r"(?is)^SELECT\s", statement):
        raise ValueError("ERP statements must be a single SELECT")
    if ";" in statement or "--" in statement or "/*" in statement:
        raise ValueError("ERP statements must be a single SELECT without separators or comments")
    match = _FORBIDDEN.search(statement)
    if match:
        raise ValueError(f"ERP statements must not contain {match.group(0).upper()}")
    return statement


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (Decimal, datetime, int)) or value is None:
        return value
    return str(value)


def _braced(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


class SqlServerErpReader:
    name = "sqlserver"

    def __init__(self, settings: Settings, *, driver: ModuleType | None = None) -> None:
        missing = [
            name for name, value in (
                ("ERP_HOST", settings.erp_host), ("ERP_USERNAME", settings.erp_username),
                ("ERP_PASSWORD", settings.erp_password and settings.erp_password.get_secret_value()),
            ) if not value
        ]
        if missing:
            raise ErpNotConfigured("ERP connection is enabled but not fully configured", details={"missing": missing})
        self._settings = settings
        self._driver = driver

    def _load_driver(self) -> ModuleType:
        if self._driver is None:
            try:
                import pyodbc  # type: ignore[import-not-found]
            except ImportError:
                raise ErpNotConfigured(
                    "ERP driver is not installed (pip install -r requirements-erp.txt)"
                ) from None
            self._driver = pyodbc
        return self._driver

    def _connection_string(self, database: str) -> str:
        s = self._settings
        return ";".join([
            f"DRIVER={_braced(s.erp_odbc_driver)}",
            f"SERVER={_braced(f'{s.erp_host},{s.erp_port}')}",
            f"DATABASE={_braced(database)}",
            f"UID={_braced(s.erp_username or '')}",
            f"PWD={_braced(s.erp_password.get_secret_value() if s.erp_password else '')}",
            f"Encrypt={'yes' if s.erp_encrypt else 'no'}",
            f"TrustServerCertificate={'yes' if s.erp_trust_server_certificate else 'no'}",
            "ApplicationIntent=ReadOnly",
            "APP=SourceOne-ReadOnly",
        ])

    def _select(self, database: str, sql: str, columns: Sequence[str]) -> list[ErpRow]:
        statement = assert_read_only(sql)
        driver = self._load_driver()
        try:
            connection = driver.connect(
                self._connection_string(database), autocommit=False, readonly=True,
                timeout=self._settings.erp_login_timeout_seconds,
            )
        except driver.Error:
            raise ErpUnavailable("Could not open a read-only connection to the ERP") from None
        try:
            connection.timeout = self._settings.erp_query_timeout_seconds
            cursor = connection.cursor()
            cursor.execute(statement)
            names = [description[0] for description in cursor.description]
            if set(names) != set(columns):
                raise ErpUnavailable("ERP returned an unexpected column set", details={"expected": list(columns)})
            return [
                {name: _clean(value) for name, value in zip(names, record)}
                for record in cursor.fetchall()
            ]
        except driver.Error:
            raise ErpUnavailable("ERP read failed") from None
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()

    def latest_price_snapshot(self) -> list[ErpRow]:
        return self._select(self._settings.erp_price_database, PRICE_SNAPSHOT_SQL, PRICE_COLUMNS)

    def domestic_grades(self) -> list[ErpRow]:
        return self._select(self._settings.erp_price_database, GRADES_SQL, GRADE_COLUMNS)

    def customers(self) -> list[ErpRow]:
        return self._select(self._settings.erp_customer_database, CUSTOMERS_SQL, CUSTOMER_COLUMNS)
