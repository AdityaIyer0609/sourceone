"""Pure helpers that consume a benchmark without turning it into a transaction price."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.core.errors import CurrencyUnitMismatch, ValidationFailed
from app.pricing.constants import ESTIMATE_LABEL, ESTIMATE_PRICE_KIND
from app.pricing.read_model import CurrentBenchmark

AMOUNT_QUANTUM = Decimal("0.01")
PRICE_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True)
class PriceTerms:
    amount: Decimal
    currency: str
    unit: str
    price_basis: str
    tax_basis: str


@dataclass(frozen=True)
class BenchmarkComparison:
    state: str  # "comparable" | "not_comparable"
    mismatches: tuple[str, ...] = ()
    difference: Decimal | None = None
    direction: str | None = None  # "below" | "above" | "equal"
    percent: Decimal | None = None


def compare_offer_to_benchmark(offer: PriceTerms, benchmark: PriceTerms) -> BenchmarkComparison:
    """Like-for-like only: no freight, tax or currency adjustment is ever applied."""
    mismatches = tuple(
        name
        for name in ("currency", "unit", "price_basis", "tax_basis")
        if getattr(offer, name) != getattr(benchmark, name)
    )
    if mismatches:
        return BenchmarkComparison(state="not_comparable", mismatches=mismatches)
    difference = (offer.amount - benchmark.amount).quantize(PRICE_QUANTUM)
    direction = "below" if difference < 0 else "above" if difference > 0 else "equal"
    percent = (abs(difference) / benchmark.amount * 100).quantize(Decimal("0.01"))
    return BenchmarkComparison(
        state="comparable", difference=abs(difference), direction=direction, percent=percent
    )


@dataclass(frozen=True)
class EstimatedMaterialValue:
    """quantity × current benchmark. Informational only; never a listing, offer or PO price."""

    quantity: Decimal
    unit: str
    currency: str
    unit_value: Decimal
    amount: Decimal
    benchmark_id: uuid.UUID
    freshness_state: str
    price_kind: str = ESTIMATE_PRICE_KIND
    label: str = ESTIMATE_LABEL
    informational: bool = True


def estimate_material_value(
    quantity: Decimal, quantity_unit: str, current: CurrentBenchmark
) -> EstimatedMaterialValue | None:
    if quantity <= 0:
        raise ValidationFailed("Quantity must be greater than zero")
    if current.benchmark is None or current.freshness is None:
        return None
    benchmark = current.benchmark
    if quantity_unit != benchmark.unit:
        raise CurrencyUnitMismatch(
            f"Quantity must be expressed in {benchmark.unit}",
            details={"expected": benchmark.unit, "received": quantity_unit},
        )
    return EstimatedMaterialValue(
        quantity=quantity,
        unit=benchmark.unit,
        currency=benchmark.currency,
        unit_value=benchmark.value,
        amount=(quantity * benchmark.value).quantize(AMOUNT_QUANTUM),
        benchmark_id=benchmark.id,
        freshness_state=current.freshness.state,
    )
