"""Display-only commercial charges. These figures are never written onto an offer or an order total."""

from decimal import Decimal, ROUND_HALF_UP

# Plastics are quoted GST extra. This is a Plenza display rule, not an ERP tax code.
GST_RATE_PERCENT = Decimal("18")
GST_WITH_FREIGHT = "GST extra at 18% on material and estimated freight"
GST_MATERIAL_ONLY = "GST extra at 18% on material only, because freight is on request"


def _cents(amount: Decimal) -> int:
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _money(cents: int) -> Decimal:
    return (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"))


def display_charges(material: Decimal, freight: Decimal | None) -> dict:
    """GST on material, plus estimated freight when that freight is known."""
    material_cents = _cents(material)
    freight_cents = _cents(freight) if freight is not None else None
    base = material_cents + (freight_cents or 0)
    product = base * int(GST_RATE_PERCENT)
    gst_cents = product // 100
    if (product % 100) * 2 >= 100:
        gst_cents += 1
    return {
        "material": _money(material_cents),
        "freight": _money(freight_cents) if freight_cents is not None else None,
        "gst_rate_percent": int(GST_RATE_PERCENT),
        "gst_basis": GST_WITH_FREIGHT if freight is not None else GST_MATERIAL_ONLY,
        "gst": _money(gst_cents),
        "payable": _money(base + gst_cents),
    }
