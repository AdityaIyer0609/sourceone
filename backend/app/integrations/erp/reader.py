"""The ERP reader contract. Readers only return rows; there is deliberately no write, update or sync-back API."""

from collections.abc import Mapping
from typing import Any, Protocol

ErpRow = Mapping[str, Any]


class ErpReader(Protocol):
    name: str

    def latest_price_snapshot(self) -> list[ErpRow]:
        """DomesticPrice1 rows from the latest price date (every row on the day of MAX(SysDate))."""
        ...

    def domestic_grades(self) -> list[ErpRow]:
        """DomesticGrade reference rows, keyed by GRADE_COLUMNS."""
        ...

    def customers(self) -> list[ErpRow]:
        """Customer identity rows, keyed by CUSTOMER_COLUMNS."""
        ...
