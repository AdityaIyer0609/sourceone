"""Order suppliers by estimated total, nudged only when their history is large enough.

The adjusted figure is a sort key. It is not the amount payable.
"""

from decimal import Decimal, ROUND_HALF_UP

PENALTY_CAP = Decimal("1.25")
CREDIT_FLOOR = Decimal("0.95")
CREDIT = Decimal("0.05")


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _ratio(percent: str) -> Decimal:
    return Decimal(percent) / Decimal(100)


def _usable(rate: dict, minimum: int) -> bool:
    return bool(rate.get("available")) and int(rate.get("total") or 0) >= minimum and rate.get("percent") is not None


def _reply_share(hours: Decimal) -> Decimal:
    if hours <= 24:
        return Decimal(0)
    if hours >= 72:
        return Decimal(1)
    return (hours - 24) / Decimal(48)


def comparison_factor(rates: dict) -> tuple[Decimal, list[str]]:
    """1.00 with no history. At most 5% in their favour, and at most 25% against them."""
    penalty = Decimal(0)
    notes: list[str] = []
    acceptance = rates.get("acceptance") or {}
    cancellation = rates.get("order_cancellation") or {}
    quality = rates.get("quality") or {}
    response = rates.get("response_time") or {}

    if _usable(acceptance, 5):
        share = _ratio(acceptance["percent"])
        penalty += Decimal("0.10") * (Decimal(1) - share)
        notes.append(
            f"Acceptance {acceptance['percent']}% from {acceptance['count']} of {acceptance['total']} decided negotiations"
        )
    if _usable(cancellation, 5):
        penalty += Decimal("0.08") * _ratio(cancellation["percent"])
        notes.append(
            f"Order cancellation {cancellation['percent']}% from {cancellation['count']} of {cancellation['total']} orders"
        )
    if _usable(quality, 3):
        penalty += Decimal("0.04") * _ratio(quality["percent"])
        notes.append(
            f"Rejected documents {quality['percent']}% from {quality['count']} of {quality['total']} files"
        )
    samples = int(response.get("sample_count") or 0)
    if response.get("available") and samples >= 5 and response.get("average_hours"):
        hours = Decimal(response["average_hours"])
        share = _reply_share(hours)
        penalty += Decimal("0.03") * share
        if share > 0:
            notes.append(f"Average reply is {response['average_hours']} hours from {samples} replies")

    credit = Decimal(0)
    acceptance_strong = _usable(acceptance, 5) and _ratio(acceptance["percent"]) >= Decimal("0.80")
    cancellation_ok = not _usable(cancellation, 5) or _ratio(cancellation["percent"]) <= Decimal("0.10")
    quality_ok = not _usable(quality, 3) or _ratio(quality["percent"]) <= Decimal("0.10")
    if acceptance_strong and cancellation_ok and quality_ok:
        credit = CREDIT
        notes.append("Strong acceptance record")

    if not notes:
        notes.append("No history yet")

    factor = Decimal(1) + penalty - credit
    if factor > PENALTY_CAP:
        factor = PENALTY_CAP
    if factor < CREDIT_FLOOR:
        factor = CREDIT_FLOOR
    return factor.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), notes


def adjusted_total(landed: Decimal, factor: Decimal) -> Decimal:
    return _money(landed * factor)
