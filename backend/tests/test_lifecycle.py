from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.errors import (
    CurrencyUnitMismatch,
    DuplicateEffectiveFrom,
    FourEyesRequired,
    InvalidStateTransition,
    PermissionDenied,
    PublishedBenchmarkImmutable,
    SeriesMismatch,
    StaleRowVersion,
    ValidationFailed,
)
from app.pricing import repository, service
from app.pricing.constants import BenchmarkMethod, BenchmarkOrigin, BenchmarkStatus

D1, D2 = date(2026, 9, 1), date(2026, 9, 8)


def _selected(world, value="97.50", as_of=D1, actor="alice", **kwargs):
    rate = world.ingest(as_of, [world.row(1, value), world.row(2, "96.00", producer="B")]).source_rates[0]
    return service.select_source_rate(world.session, world.actors[actor], source_rate_id=rate.id, **kwargs), rate


def _published(world, **kwargs):
    benchmark, _ = _selected(world, **kwargs)
    service.submit_benchmark(world.session, world.actors["alice"], benchmark.id)
    return service.publish_benchmark(world.session, world.actors["alice"], benchmark.id)


# --- creation --------------------------------------------------------------------------------


def test_selecting_a_source_rate_creates_an_untouched_draft(world):
    benchmark, rate = _selected(world)
    assert benchmark.status == BenchmarkStatus.DRAFT
    assert benchmark.method == BenchmarkMethod.ADOPTED
    assert benchmark.origin == BenchmarkOrigin.SYSTEM_SUGGESTION
    assert not benchmark.is_edited and not benchmark.four_eyes_required
    assert benchmark.value == rate.value and benchmark.source_as_of_date == D1
    assert repository.primary_input(benchmark).source_rate_id == rate.id


def test_manual_benchmark_is_human_and_needs_four_eyes(world):
    benchmark = world.manual("alice", value="101.2")
    assert benchmark.method == BenchmarkMethod.MANUAL and benchmark.origin == BenchmarkOrigin.HUMAN
    assert benchmark.four_eyes_required and benchmark.value == Decimal("101.2000")
    with pytest.raises(ValidationFailed):
        world.manual("alice", reason=" ")


def test_buyers_and_suppliers_cannot_create_or_publish(world):
    rate = world.ingest(D1, [world.row(1, "97.50")]).source_rates[0]
    for who in ("buyer", "supplier"):
        with pytest.raises(PermissionDenied):
            service.select_source_rate(world.session, world.actors[who], source_rate_id=rate.id)
    suggestion = repository.get_benchmark(world.session, _suggestion_id(world, rate))
    with pytest.raises(PermissionDenied):
        service.publish_benchmark(world.session, world.actors["buyer"], suggestion.id)


def _suggestion_id(world, rate):
    return world.session.execute(
        text("SELECT benchmark_rate_id FROM benchmark_rate_inputs WHERE source_rate_id = :id"), {"id": rate.id}
    ).scalar_one()


# --- lifecycle -------------------------------------------------------------------------------


def test_untouched_selection_can_be_published_by_one_publisher(world):
    benchmark = _published(world)
    assert benchmark.status == BenchmarkStatus.PUBLISHED
    assert benchmark.published_by_id == world.users["alice"].id
    assert benchmark.staleness_days == 14
    events = [e.action for e in repository.audit_events(world.session, entity_id=benchmark.id)]
    assert set(events) == {"created", "submitted", "published"}


def test_system_suggestion_is_published_by_a_single_publisher(world):
    suggestion = world.ingest(D1, [world.row(1, "97.50")]).suggestions[0]
    assert suggestion.status == BenchmarkStatus.SUBMITTED and not suggestion.four_eyes_required
    published = service.publish_benchmark(world.session, world.actors["bob"], suggestion.id)
    assert published.status == BenchmarkStatus.PUBLISHED


def test_reject_from_draft_and_submitted_requires_reason(world):
    draft, _ = _selected(world)
    with pytest.raises(ValidationFailed):
        service.reject_benchmark(world.session, world.actors["bob"], draft.id, reason="")
    rejected = service.reject_benchmark(world.session, world.actors["bob"], draft.id, reason="Wrong producer")
    assert rejected.status == BenchmarkStatus.REJECTED and rejected.rejected_reason == "Wrong producer"

    manual = world.manual("alice", as_of=D2)
    service.submit_benchmark(world.session, world.actors["alice"], manual.id)
    rejected = service.reject_benchmark(world.session, world.actors["bob"], manual.id, reason="No evidence")
    assert rejected.status == BenchmarkStatus.REJECTED


def test_withdraw_published_benchmark(world):
    benchmark = _published(world)
    withdrawn = service.withdraw_benchmark(world.session, world.actors["bob"], benchmark.id, reason="Circular revised")
    assert withdrawn.status == BenchmarkStatus.WITHDRAWN
    assert withdrawn.withdrawn_reason == "Circular revised"


@pytest.mark.parametrize(
    ("setup", "action"),
    [
        ("draft", "publish"),
        ("draft", "withdraw"),
        ("submitted", "withdraw"),
        ("submitted", "submit"),
        ("published", "submit"),
        ("published", "reject"),
        ("published", "publish"),
        ("withdrawn", "withdraw"),
        ("withdrawn", "publish"),
        ("rejected", "submit"),
        ("rejected", "publish"),
    ],
)
def test_invalid_transitions_are_blocked(world, setup, action):
    session, alice, bob = world.session, world.actors["alice"], world.actors["bob"]
    benchmark, _ = _selected(world)
    if setup in ("submitted", "published", "withdrawn"):
        service.submit_benchmark(session, alice, benchmark.id)
    if setup in ("published", "withdrawn"):
        service.publish_benchmark(session, alice, benchmark.id)
    if setup == "withdrawn":
        service.withdraw_benchmark(session, bob, benchmark.id, reason="Test withdraw")
    if setup == "rejected":
        service.reject_benchmark(session, bob, benchmark.id, reason="Test reject")

    calls = {
        "submit": lambda: service.submit_benchmark(session, alice, benchmark.id),
        "publish": lambda: service.publish_benchmark(session, bob, benchmark.id),
        "reject": lambda: service.reject_benchmark(session, bob, benchmark.id, reason="Too late"),
        "withdraw": lambda: service.withdraw_benchmark(session, bob, benchmark.id, reason="Again"),
    }
    with pytest.raises(InvalidStateTransition):
        calls[action]()


# --- immutability ----------------------------------------------------------------------------


def test_published_benchmark_cannot_be_edited_via_service(world):
    benchmark = _published(world)
    with pytest.raises(PublishedBenchmarkImmutable):
        service.edit_benchmark(world.session, world.actors["alice"], benchmark.id,
                               row_version=benchmark.row_version, value=Decimal("1"), reason="Fix")


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE benchmark_rates SET value = value + 1 WHERE id = :id",
        "UPDATE benchmark_rates SET effective_from = effective_from - interval '1 day' WHERE id = :id",
        "UPDATE benchmark_rates SET status = 'draft' WHERE id = :id",
        "DELETE FROM benchmark_rates WHERE id = :id",
        "DELETE FROM benchmark_rate_inputs WHERE benchmark_rate_id = :id",
        "UPDATE pricing_audit_events SET reason = 'tampered' WHERE entity_id = :id",
        "DELETE FROM pricing_audit_events WHERE entity_id = :id",
    ],
)
def test_database_rejects_tampering_with_published_records(world, statement):
    benchmark = _published(world)
    with pytest.raises(DBAPIError):
        with world.session.begin_nested():
            world.session.execute(text(statement), {"id": benchmark.id})


def test_database_allows_only_shortening_effective_until(world):
    benchmark = _published(world)
    session = world.session
    later = benchmark.effective_from + timedelta(days=30)
    with session.begin_nested():
        session.execute(text("UPDATE benchmark_rates SET effective_until = :u WHERE id = :id"),
                        {"u": later, "id": benchmark.id})
    with pytest.raises(DBAPIError):
        with session.begin_nested():
            session.execute(text("UPDATE benchmark_rates SET effective_until = :u WHERE id = :id"),
                            {"u": later + timedelta(days=1), "id": benchmark.id})


def test_database_rejects_changing_source_rate_facts(world):
    rate = world.ingest(D1, [world.row(1, "97.50")]).source_rates[0]
    with pytest.raises(DBAPIError):
        with world.session.begin_nested():
            world.session.execute(text("UPDATE source_rates SET value = 1 WHERE id = :id"), {"id": rate.id})


def test_stale_row_version_is_rejected(world):
    benchmark, _ = _selected(world)
    with pytest.raises(StaleRowVersion):
        service.edit_benchmark(world.session, world.actors["alice"], benchmark.id,
                               row_version=benchmark.row_version + 1, value=Decimal("99"), reason="Adjust")


# --- four-eyes -------------------------------------------------------------------------------


def test_value_edit_requires_a_different_publisher(world):
    session, alice, bob = world.session, world.actors["alice"], world.actors["bob"]
    benchmark, _ = _selected(world)
    service.edit_benchmark(session, alice, benchmark.id, row_version=benchmark.row_version,
                           value=Decimal("98.10"), reason="Producer phoned in a correction")
    assert benchmark.is_edited and benchmark.four_eyes_required and benchmark.method == BenchmarkMethod.MANUAL
    service.submit_benchmark(session, alice, benchmark.id)
    with pytest.raises(FourEyesRequired):
        service.publish_benchmark(session, alice, benchmark.id)
    assert service.publish_benchmark(session, bob, benchmark.id).status == BenchmarkStatus.PUBLISHED


def test_editing_a_system_suggestion_blocks_the_editor_from_publishing(world):
    session, alice, bob = world.session, world.actors["alice"], world.actors["bob"]
    suggestion = world.ingest(D1, [world.row(1, "97.50")]).suggestions[0]
    service.edit_benchmark(session, bob, suggestion.id, row_version=suggestion.row_version,
                           effective_from=suggestion.effective_from + timedelta(hours=12))
    assert suggestion.four_eyes_required
    with pytest.raises(FourEyesRequired):
        service.publish_benchmark(session, bob, suggestion.id)
    assert service.publish_benchmark(session, alice, suggestion.id).status == BenchmarkStatus.PUBLISHED


def test_selection_with_changed_dates_requires_four_eyes(world):
    benchmark, rate = _selected(world, effective_until=None)
    assert not benchmark.four_eyes_required
    other = service.select_source_rate(
        world.session, world.actors["alice"], source_rate_id=rate.id,
        effective_from=benchmark.effective_from + timedelta(days=1),
    )
    assert other.is_edited and other.four_eyes_required


def test_manual_benchmark_needs_a_second_publisher(world):
    session = world.session
    manual = world.manual("alice")
    service.submit_benchmark(session, world.actors["alice"], manual.id)
    with pytest.raises(FourEyesRequired):
        service.publish_benchmark(session, world.actors["alice"], manual.id)
    published = service.publish_benchmark(session, world.actors["platform"], manual.id)
    assert published.staleness_days == 7


# --- validation ------------------------------------------------------------------------------


def test_duplicate_effective_date_is_rejected(world):
    session = world.session
    first, rate = _selected(world)
    rival = service.select_source_rate(session, world.actors["bob"],
                                       source_rate_id=_other_producer_rate(world, rate))
    service.submit_benchmark(session, world.actors["alice"], first.id)
    service.publish_benchmark(session, world.actors["alice"], first.id)
    service.submit_benchmark(session, world.actors["bob"], rival.id)
    with pytest.raises(DuplicateEffectiveFrom):
        service.publish_benchmark(session, world.actors["bob"], rival.id)
    with pytest.raises(DuplicateEffectiveFrom):
        world.manual("alice", as_of=D1)
    with pytest.raises(DuplicateEffectiveFrom):
        service.select_source_rate(session, world.actors["bob"], source_rate_id=rate.id)


def _other_producer_rate(world, rate):
    return world.session.execute(
        text("SELECT id FROM source_rates WHERE import_batch_id = :b AND id <> :id"),
        {"b": rate.import_batch_id, "id": rate.id},
    ).scalar_one()


@pytest.mark.parametrize(("currency", "unit"), [("USD", "KG"), ("INR", "MT")])
def test_currency_or_unit_mismatch_is_rejected(world, currency, unit):
    with pytest.raises(CurrencyUnitMismatch):
        world.manual("alice", currency=currency, unit=unit)


def test_source_rate_for_another_series_is_rejected(world):
    rate = world.ingest(D1, [world.import_row(1, "1.085")]).source_rates[0]
    with pytest.raises(SeriesMismatch):
        service.select_source_rate(world.session, world.actors["alice"], source_rate_id=rate.id,
                                   series_id=world.series["inr"].id)
