"""Demo payment adjustment on the material unit price. Freight and GST stay separate."""

from decimal import Decimal, ROUND_HALF_UP

# Advance is cheaper. Later payment costs more. Nothing past 14 days is offered.
RATES = {
    "Advance": Decimal("-0.0100"),
    "1-2 days": Decimal("0.0025"),
    "3-4 days": Decimal("0.0050"),
    "5-7 days": Decimal("0.0100"),
    "8-14 days": Decimal("0.0150"),
}


def adjust_unit_price(amount: Decimal, terms: str | None) -> Decimal:
    rate = RATES.get((terms or "").strip(), Decimal(0))
    if rate == 0:
        return amount
    return (amount * (Decimal(1) + rate)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
