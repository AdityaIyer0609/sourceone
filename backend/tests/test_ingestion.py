from datetime import date
from decimal import Decimal

import pytest

from app.core.errors import SourceInactive, SourceRateNotEligible, SourceRateUnresolved
from app.pricing import service
from app.pricing.constants import BenchmarkStatus, ResolutionStatus
from tests.factories import build_world
from tests.test_api import as_user

D1, D2 = date(2026, 9, 1), date(2026, 9, 8)


def test_configured_field_keeps_other_erp_prices_and_does_not_publish(world):
    profile = dict(world.erp_source.normalization_profile)
    profile["benchmark_field"] = "GrandTotal"
    profile["value_field"] = "GrandTotal"
    profile["must_equal_fields"] = []
    world.erp_source.normalization_profile = profile
    row = world.row(1, "97.50", UnitPrice="90.00", Basic="91.00", Total="96.00", GrandTotal="97.50")
    result = world.ingest(D1, [row])
    rate = result.source_rates[0]
    assert rate.resolution_status == ResolutionStatus.RESOLVED
    assert rate.value == Decimal("97.5000")
    assert rate.raw_payload["benchmarkField"] == "GrandTotal"
    assert rate.raw_payload["row"]["UnitPrice"] == "90.00"
    assert rate.raw_payload["row"]["Basic"] == "91.00"
    assert rate.raw_payload["row"]["Total"] == "96.00"
    assert rate.raw_payload["row"]["GrandTotal"] == "97.50"
    assert result.suggestions[0].status == BenchmarkStatus.SUBMITTED
    assert result.suggestions[0].published_at is None


def test_platform_admin_sets_the_benchmark_field(client, world):
    url = f"/api/v1/admin/pricing/sources/{world.erp_source.id}/benchmark-field"
    denied = client.patch(url, json={"benchmarkPriceField": "Total"}, headers=as_user(world, "alice"))
    assert denied.status_code == 403
    saved = client.patch(url, json={"benchmarkPriceField": "Total"}, headers=as_user(world, "platform"))
    assert saved.status_code == 200, saved.text
    assert saved.json()["benchmarkPriceField"] == "Total"
    world.session.refresh(world.erp_source)
    assert world.erp_source.normalization_profile["benchmark_field"] == "Total"
    assert world.erp_source.normalization_profile["must_equal_fields"] == []
    row = world.row(1, "97.50", UnitPrice="90.00", Basic="91.00", Total="96.00", GrandTotal="99.00")
    rate = world.ingest(D1, [row]).source_rates[0]
    assert rate.value == Decimal("96.0000") and rate.resolution_status == ResolutionStatus.RESOLVED


def test_domestic_row_creates_resolved_eligible_source_rate(world):
    result = world.ingest(D1, [world.row(1, "97.5")])
    rate = result.source_rates[0]
    assert rate.resolution_status == ResolutionStatus.RESOLVED
    assert rate.is_benchmark_eligible
    assert rate.series_id == world.series["inr"].id
    assert rate.value == Decimal("97.5000")
    assert (rate.currency, rate.unit, rate.sector) == ("INR", "KG", "DOMESTIC")
    assert (rate.price_basis, rate.tax_basis) == ("DELIVERED", "GST_EXCLUDED")
    assert rate.source_as_of_date == D1
    assert rate.source_row_ref == "DomesticPrice1:SrNo=1"
    assert rate.origin_location == "Plant"
    assert result.batch.resolved_count == 1 and result.batch.status == "succeeded"


def test_deemed_rows_are_stored_but_never_benchmark_eligible(world):
    result = world.ingest(D1, [world.row(1, "97.50"), world.row(2, "88.70", sector="Deemed")])
    domestic, deemed = result.source_rates
    assert deemed.resolution_status == ResolutionStatus.RESOLVED
    assert not deemed.is_benchmark_eligible
    assert deemed.eligibility_reason == "sector_not_eligible"
    assert deemed.series_id is None
    # Deemed does not compete with Domestic, so the single Domestic row becomes the suggestion.
    assert len(result.suggestions) == 1
    assert result.suggestions[0].value == domestic.value
    with pytest.raises(SourceRateNotEligible):
        service.select_source_rate(world.session, world.actors["alice"], source_rate_id=deemed.id)


def test_import_eligibility_is_profile_driven(db):
    eligible = build_world(db, import_eligible=True)
    rate = eligible.ingest(D1, [eligible.import_row(1, "1.085")]).source_rates[0]
    assert rate.is_benchmark_eligible and rate.series_id == eligible.series["usd"].id
    assert rate.currency == "USD" and rate.price_basis == "IMPORT_ORIGIN"

    ineligible = build_world(db, import_eligible=False)
    rate = ineligible.ingest(D1, [ineligible.import_row(1, "1.085")]).source_rates[0]
    assert rate.resolution_status == ResolutionStatus.RESOLVED and not rate.is_benchmark_eligible


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"Basic": "98.00"}, "price_fields_diverged"),
        ({"Frieght": "1.50"}, "unexpected_components"),
        ({"Currency": "EUR"}, "unsupported_currency"),
        ({"Sector": "Export"}, "unknown_sector"),
        ({"Grade": "NOPE-9"}, "unknown_grade"),
        ({"Location": "Plant to Nowhere"}, "unknown_market"),
        ({"Company": "Unknown Co"}, "unknown_producer"),
    ],
)
def test_unresolvable_rows_are_kept_as_unresolved(world, overrides, reason):
    rate = world.ingest(D1, [world.row(1, "97.50", **overrides)]).source_rates[0]
    assert rate.resolution_status == ResolutionStatus.UNRESOLVED
    assert rate.resolution_reason == reason
    assert not rate.is_benchmark_eligible
    with pytest.raises((SourceRateUnresolved, SourceRateNotEligible)):
        service.select_source_rate(world.session, world.actors["alice"], source_rate_id=rate.id)


def test_row_without_series_is_unresolved(world):
    rate = world.ingest(D1, [world.row(1, "97.50", location=world.import_market_text)]).source_rates[0]
    assert rate.resolution_reason == "no_series"


def test_reimporting_the_same_batch_is_idempotent(world):
    rows = [world.row(1, "97.50")]
    first = world.ingest(D1, rows)
    again = world.ingest(D1, rows)
    assert again.duplicate and again.batch.id == first.batch.id


def test_unchanged_reentry_is_kept_but_creates_no_benchmark_point(world):
    first = world.ingest(D1, [world.row(1, "97.50")])
    second = world.ingest(D2, [world.row(1, "97.50")])
    assert len(first.suggestions) == 1
    assert second.source_rates[0].is_unchanged
    assert second.suggestions == []
    changed = world.ingest(date(2026, 9, 15), [world.row(1, "98.00")])
    assert not changed.source_rates[0].is_unchanged and len(changed.suggestions) == 1


def test_changed_row_identity_for_same_row_key_is_unresolved(world):
    world.ingest(D1, [world.row(1, "97.50")])
    rate = world.ingest(D2, [world.row(1, "97.50", producer="B")]).source_rates[0]
    assert rate.resolution_reason == "row_identity_changed"


def test_multiple_producers_need_an_admin_choice(world):
    result = world.ingest(D1, [world.row(1, "97.50"), world.row(2, "97.20", producer="B")])
    assert result.suggestions == []
    assert all(r.is_benchmark_eligible for r in result.source_rates)


def test_inactive_source_blocks_ingestion_and_publishing(world):
    suggestion = world.ingest(D1, [world.row(1, "97.50")]).suggestions[0]
    assert suggestion.status == BenchmarkStatus.SUBMITTED
    world.erp_source.is_active = False
    world.session.flush()
    with pytest.raises(SourceInactive):
        world.ingest(D2, [world.row(1, "98.00")])
    with pytest.raises(SourceInactive):
        service.publish_benchmark(world.session, world.actors["bob"], suggestion.id)
