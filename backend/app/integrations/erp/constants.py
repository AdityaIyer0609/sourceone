from enum import StrEnum


class IntegrationPermission(StrEnum):
    ERP_SYNC = "integration.erp.sync"


class SyncRunStatus(StrEnum):
    SUCCEEDED = "succeeded"


class GradeMappingStatus(StrEnum):
    MAPPED = "mapped"
    UNMAPPED_PRODUCER = "unmapped_producer"
    UNMAPPED_GRADE = "unmapped_grade"


# The only DomesticPrice1 columns SourceOne reads and keeps (identity, grade/market identity, price).
PRICE_COLUMNS = (
    "SrNo", "SysDate", "Company", "Quality", "Grade", "Location", "Sector", "Appilcation", "Currency",
    "CurrencyCon", "UnitPrice", "Basic", "Total", "GrandTotal", "CashDis", "LocDis", "Trade", "Special",
    "QD", "AQD", "MOU", "Frieght", "GSTPER", "GSTAMT", "QtySlab",
)
GRADE_COLUMNS = ("SrNo", "Company", "Quality", "Grade", "MFI", "Density", "ItemCode")
# Customer identity only. Bank, PAN, ledger, credit and payment fields are never read.
CUSTOMER_COLUMNS = ("CompanyName", "GSTIN", "PINCode")

GSTIN_PATTERN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
PIN_PATTERN = r"^[1-9][0-9]{5}$"
