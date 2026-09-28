import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.errors import CurrencyUnitMismatch
from app.models.pricing import BenchmarkRate
from app.pricing import comparison, read_model
from app.pricing.constants import BenchmarkStatus
from app.pricing.service import compute_stale_after, default_effective_from

NOW = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)


def bench(as_of: date, value: str, *, status=BenchmarkStatus.PUBLISHED, days=14, until=None, withdrawn_at=None):
    effective = default_effective_from(as_of)
    return BenchmarkRate(
        id=uuid.uuid4(), status=status, value=Decimal(value), currency="INR", unit="KG",
        price_basis="DELIVERED", tax_basis="GST_EXCLUDED", source_as_of_date=as_of,
        effective_from=effective, effective_until=until, staleness_days=days,
        stale_after=compute_stale_after(as_of, days), withdrawn_at=withdrawn_at,
    )


def test_stale_after_is_start_of_business_day_plus_staleness():
    # Start of 1 Sep in IST is 31 Aug 18:30 UTC.
    assert default_effective_from(date(2026, 9, 1)) == datetime(2026, 8, 31, 18, 30, tzinfo=UTC)
    assert compute_stale_after(date(2026, 9, 1), 14) == datetime(2026, 9, 14, 18, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("as_of", "days", "state"),
    [
        (date(2026, 9, 25), 14, "fresh"),  # ERP, 3 days old
        (date(2026, 9, 14), 14, "stale"),  # stale_after = 27 Sep 18:30 UTC < NOW
        (date(2026, 9, 15), 14, "fresh"),  # stale_after = 28 Sep 18:30 UTC > NOW
        (date(2026, 9, 21), 7, "stale"),   # manual, 7 days
    ],
)
def test_freshness(as_of, days, state):
    current = read_model.resolve_current([bench(as_of, "99", days=days)], NOW)
    assert current.availability == "available" and current.freshness.state == state


def test_current_is_latest_effective_and_ignores_future_and_unpublished():
    older, latest = bench(date(2026, 9, 10), "98"), bench(date(2026, 9, 20), "99")
    future = bench(date(2026, 10, 5), "100")
    draft = bench(date(2026, 9, 25), "101", status=BenchmarkStatus.SUBMITTED)
    current = read_model.resolve_current([older, latest, future, draft], NOW)
    assert current.benchmark is latest


def test_withdrawn_latest_gives_rate_on_request_without_fallback():
    older = bench(date(2026, 9, 10), "98")
    withdrawn = bench(date(2026, 9, 20), "99", status=BenchmarkStatus.WITHDRAWN,
                      withdrawn_at=datetime(2026, 9, 22, tzinfo=UTC))
    current = read_model.resolve_current([older, withdrawn], NOW)
    assert current.availability == "rate_on_request" and current.unavailable_reason == "withdrawn"
    assert current.benchmark is None


def test_expired_latest_gives_rate_on_request():
    expired = bench(date(2026, 9, 20), "99", until=datetime(2026, 9, 25, tzinfo=UTC))
    current = read_model.resolve_current([bench(date(2026, 9, 10), "98"), expired], NOW)
    assert current.unavailable_reason == "expired"


def test_history_statistics_require_minimum_points():
    one = read_model.build_history([bench(date(2026, 9, 20), "99")], "1M", NOW, min_points=2, volatility_min_points=5)
    assert one.state == "insufficient_data" and one.stats.point_count == 1

    series = [bench(date(2026, 9, d), v) for d, v in ((5, "97"), (12, "98"), (19, "99"))]
    history = read_model.build_history(series, "1M", NOW, min_points=2, volatility_min_points=5)
    assert history.stats.state == "ok"
    assert (history.stats.high, history.stats.low) == (Decimal("99"), Decimal("97"))
    assert history.stats.volatility_state == "insufficient_data"


def test_history_carry_in_and_withdrawal_gap():
    carried = bench(date(2026, 9, 1), "97")
    withdrawn = bench(date(2026, 9, 24), "99", status=BenchmarkStatus.WITHDRAWN,
                      withdrawn_at=datetime(2026, 9, 25, tzinfo=UTC))
    history = read_model.build_history([carried, withdrawn], "7D", NOW, min_points=2, volatility_min_points=5)
    assert history.carry_in is not None and history.carry_in.value == Decimal("97")
    assert history.points == []
    assert [g.reason for g in history.gaps] == ["withdrawn"]


def test_movement_against_previous_published():
    current = read_model.resolve_current([bench(date(2026, 9, 10), "98.00"), bench(date(2026, 9, 20), "99.47")], NOW)
    move = read_model.movement([current.benchmark, bench(date(2026, 9, 10), "98.00")], current)
    assert move.absolute == Decimal("1.4700") and move.percent == Decimal("1.50")


def terms(amount="99", currency="INR", unit="KG", basis="DELIVERED", tax="GST_EXCLUDED"):
    return comparison.PriceTerms(Decimal(amount), currency, unit, basis, tax)


def test_like_for_like_comparison():
    result = comparison.compare_offer_to_benchmark(terms("97.02"), terms("99"))
    assert result.state == "comparable" and result.direction == "below" and result.percent == Decimal("2.00")


@pytest.mark.parametrize(
    ("offer", "mismatch"),
    [
        (terms(currency="USD"), "currency"),
        (terms(unit="MT"), "unit"),
        (terms(basis="EX_WORKS"), "price_basis"),
        (terms(tax="GST_INCLUDED"), "tax_basis"),
    ],
)
def test_comparison_across_terms_is_not_comparable(offer, mismatch):
    result = comparison.compare_offer_to_benchmark(offer, terms())
    assert result.state == "not_comparable" and result.mismatches == (mismatch,) and result.difference is None


def test_estimated_material_value():
    current = read_model.resolve_current([bench(date(2026, 9, 25), "99.40")], NOW)
    estimate = comparison.estimate_material_value(Decimal("25000"), "KG", current)
    assert estimate.amount == Decimal("2485000.00") and estimate.price_kind == "estimated_material_value"
    assert estimate.label == "Estimated material value at SourceOne benchmark" and estimate.informational
    with pytest.raises(CurrencyUnitMismatch):
        comparison.estimate_material_value(Decimal("25"), "MT", current)
    unavailable = read_model.resolve_current([], NOW)
    assert comparison.estimate_material_value(Decimal("1"), "KG", unavailable) is None
