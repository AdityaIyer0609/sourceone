"""In-memory ERP reader for tests and local development. Holds fixture rows; never connects anywhere."""

import copy
from collections.abc import Sequence

from app.integrations.erp.reader import ErpRow


class MockErpReader:
    name = "mock"

    def __init__(
        self,
        *,
        prices: Sequence[ErpRow] = (),
        grades: Sequence[ErpRow] = (),
        customers: Sequence[ErpRow] = (),
    ) -> None:
        self.prices = [dict(r) for r in prices]
        self.grades = [dict(r) for r in grades]
        self.customer_rows = [dict(r) for r in customers]
        self.calls: list[str] = []

    def latest_price_snapshot(self) -> list[ErpRow]:
        self.calls.append("latest_price_snapshot")
        return copy.deepcopy(self.prices)

    def domestic_grades(self) -> list[ErpRow]:
        self.calls.append("domestic_grades")
        return copy.deepcopy(self.grades)

    def customers(self) -> list[ErpRow]:
        self.calls.append("customers")
        return copy.deepcopy(self.customer_rows)
