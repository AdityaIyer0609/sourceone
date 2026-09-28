"""Benchmark lifecycle: candidate creation, editing, submission, publishing, rejection, withdrawal.

Every rule that protects published data (state machine, four-eyes, immutability) is enforced here,
so it holds regardless of which client calls the service.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import start_of_business_day, utcnow
from app.core.errors import (
    CurrencyUnitMismatch,
    DuplicateEffectiveFrom,
    FourEyesRequired,
    InvalidStateTransition,
    PermissionDenied,
    PublishedBenchmarkImmutable,
    SeriesMismatch,
    SourceInactive,
    SourceRateNotEligible,
    SourceRateUnresolved,
    StaleRowVersion,
    ValidationFailed,
)
from app.identity.service import Actor
from app.models.pricing import (
    BenchmarkRate,
    BenchmarkRateInput,
    PricingAuditEvent,
    RateSeries,
    RateSource,
    SourceRate,
)
from app.pricing import repository
from app.pricing.constants import (
    BENCHMARK_TRANSITIONS,
    BenchmarkMethod,
    BenchmarkOrigin,
    BenchmarkStatus,
    InputRole,
    PricingPermission,
    ResolutionStatus,
    SourceType,
)

MANUAL_SOURCE_CODE = "SOURCEONE-MANUAL"
BENCHMARK_ENTITY = "benchmark_rate"
PRICE_QUANTUM = Decimal("0.0001")


def default_effective_from(source_as_of_date: date) -> datetime:
    return start_of_business_day(source_as_of_date)


def compute_stale_after(source_as_of_date: date, staleness_days: int) -> datetime:
    return start_of_business_day(source_as_of_date) + timedelta(days=staleness_days)


def _record(
    session: Session,
    *,
    entity_id: uuid.UUID,
    action: str,
    actor_id: uuid.UUID,
    now: datetime,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    changes: dict[str, Any] | None = None,
    entity_type: str = BENCHMARK_ENTITY,
) -> None:
    session.add(
        PricingAuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            occurred_at=now,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            changes=changes,
        )
    )


def _transition(benchmark: BenchmarkRate, target: BenchmarkStatus) -> str:
    current = BenchmarkStatus(benchmark.status)
    if target not in BENCHMARK_TRANSITIONS[current]:
        raise InvalidStateTransition(
            f"Cannot move a {current} benchmark to {target}",
            details={"from": str(current), "to": str(target)},
        )
    benchmark.status = target
    return current


def _require_reason(reason: str | None, action: str) -> str:
    cleaned = (reason or "").strip()
    if len(cleaned) < 3:
        raise ValidationFailed(f"A reason is required to {action} a benchmark")
    return cleaned


def _normalise_price(value: Decimal) -> Decimal:
    value = Decimal(value).quantize(PRICE_QUANTUM)
    if value <= 0:
        raise ValidationFailed("Benchmark value must be greater than zero")
    return value


def _ensure_currency_unit(series: RateSeries, currency: str | None, unit: str | None) -> None:
    if currency != series.currency or unit != series.unit:
        raise CurrencyUnitMismatch(
            f"Series {series.code} is priced in {series.currency}/{series.unit}",
            details={
                "expected": {"currency": series.currency, "unit": series.unit},
                "received": {"currency": currency, "unit": unit},
            },
        )


def _ensure_source_active(source: RateSource) -> None:
    if not source.is_active:
        raise SourceInactive(f"Rate source {source.code} is inactive", details={"source": source.code})


def _ensure_effective_free(
    session: Session, series_id: uuid.UUID, effective_from: datetime, exclude_id: uuid.UUID | None = None
) -> None:
    if repository.effective_from_taken(
        session, series_id=series_id, effective_from=effective_from, exclude_id=exclude_id
    ):
        raise DuplicateEffectiveFrom(
            "A published benchmark already exists for this series at this effective date",
            details={"seriesId": str(series_id), "effectiveFrom": effective_from.isoformat()},
        )


def _ensure_window(effective_from: datetime, effective_until: datetime | None) -> None:
    if effective_until is not None and effective_until <= effective_from:
        raise ValidationFailed("effective_until must be later than effective_from")


def validate_source_rate_for_series(
    session: Session, source_rate: SourceRate, expected_series_id: uuid.UUID | None = None
) -> RateSeries:
    """Checks that a source rate may back a benchmark and returns its series."""
    _ensure_source_active(session.get(RateSource, source_rate.source_id))
    if source_rate.resolution_status != ResolutionStatus.RESOLVED:
        raise SourceRateUnresolved(
            "Source rate is not resolved to SourceOne reference data",
            details={"sourceRateId": str(source_rate.id), "reason": source_rate.resolution_reason},
        )
    if not source_rate.is_benchmark_eligible or source_rate.series_id is None:
        raise SourceRateNotEligible(
            "Source rate is not eligible for a buyer benchmark",
            details={"sourceRateId": str(source_rate.id), "reason": source_rate.eligibility_reason},
        )
    if expected_series_id is not None and source_rate.series_id != expected_series_id:
        raise SeriesMismatch(
            "Source rate belongs to a different series",
            details={"expected": str(expected_series_id), "actual": str(source_rate.series_id)},
        )
    series = repository.get_series(session, source_rate.series_id)
    if not series.is_active:
        raise ValidationFailed(f"Series {series.code} is inactive")
    _ensure_currency_unit(series, source_rate.currency, source_rate.unit)
    if (source_rate.price_basis, source_rate.tax_basis) != (series.price_basis, series.tax_basis):
        raise SeriesMismatch("Source rate price/tax basis does not match the series")
    return series


def _new_adopted(
    session: Session,
    *,
    source_rate: SourceRate,
    series: RateSeries,
    created_by_id: uuid.UUID,
    status: BenchmarkStatus,
    effective_from: datetime,
    effective_until: datetime | None,
    now: datetime,
) -> BenchmarkRate:
    benchmark = BenchmarkRate(
        series_id=series.id,
        primary_source_id=source_rate.source_id,
        value=source_rate.value,
        currency=series.currency,
        unit=series.unit,
        price_basis=series.price_basis,
        tax_basis=series.tax_basis,
        method=BenchmarkMethod.ADOPTED,
        origin=BenchmarkOrigin.SYSTEM_SUGGESTION,
        is_edited=False,
        four_eyes_required=False,
        status=status,
        source_as_of_date=source_rate.source_as_of_date,
        effective_from=effective_from,
        effective_until=effective_until,
        created_by_id=created_by_id,
        created_at=now,
        updated_at=now,
    )
    benchmark.inputs.append(BenchmarkRateInput(source_rate_id=source_rate.id, role=InputRole.PRIMARY))
    session.add(benchmark)
    session.flush()
    return benchmark


def create_system_suggestion(
    session: Session, *, source_rate: SourceRate, system_user_id: uuid.UUID, now: datetime | None = None
) -> BenchmarkRate | None:
    """Called by ingestion for an unambiguous, changed source rate. Returns None if the date is taken."""
    now = now or utcnow()
    series = validate_source_rate_for_series(session, source_rate)
    effective_from = default_effective_from(source_rate.source_as_of_date)
    if repository.effective_from_taken(session, series_id=series.id, effective_from=effective_from):
        return None
    benchmark = _new_adopted(
        session,
        source_rate=source_rate,
        series=series,
        created_by_id=system_user_id,
        status=BenchmarkStatus.SUBMITTED,
        effective_from=effective_from,
        effective_until=None,
        now=now,
    )
    benchmark.submitted_by_id = system_user_id
    benchmark.submitted_at = now
    _record(
        session, entity_id=benchmark.id, action="suggested", actor_id=system_user_id, now=now,
        to_status=BenchmarkStatus.SUBMITTED, changes={"sourceRateId": str(source_rate.id)},
    )
    return benchmark


def select_source_rate(
    session: Session,
    actor: Actor,
    *,
    source_rate_id: uuid.UUID,
    series_id: uuid.UUID | None = None,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    now: datetime | None = None,
) -> BenchmarkRate:
    """Admin picks one existing source rate. Untouched, it stays a system suggestion (single publisher)."""
    actor.require(PricingPermission.EDIT)
    now = now or utcnow()
    source_rate = repository.get_source_rate(session, source_rate_id)
    series = validate_source_rate_for_series(session, source_rate, series_id)

    default_from = default_effective_from(source_rate.source_as_of_date)
    resolved_from = effective_from or default_from
    _ensure_window(resolved_from, effective_until)
    _ensure_effective_free(session, series.id, resolved_from)

    benchmark = _new_adopted(
        session,
        source_rate=source_rate,
        series=series,
        created_by_id=actor.user_id,
        status=BenchmarkStatus.DRAFT,
        effective_from=resolved_from,
        effective_until=effective_until,
        now=now,
    )
    edited = resolved_from != default_from or effective_until is not None
    if edited:
        benchmark.is_edited = True
        benchmark.four_eyes_required = True
        benchmark.last_edited_by_id = actor.user_id
        benchmark.last_edited_at = now
    _record(
        session, entity_id=benchmark.id, action="created", actor_id=actor.user_id, now=now,
        to_status=BenchmarkStatus.DRAFT,
        changes={"mode": "select_source_rate", "sourceRateId": str(source_rate.id), "edited": edited},
    )
    return benchmark


def create_manual_benchmark(
    session: Session,
    actor: Actor,
    *,
    series_id: uuid.UUID,
    value: Decimal,
    currency: str,
    unit: str,
    source_as_of_date: date,
    reason: str,
    evidence_ref: str | None = None,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    source_code: str = MANUAL_SOURCE_CODE,
    now: datetime | None = None,
) -> BenchmarkRate:
    actor.require(PricingPermission.EDIT)
    now = now or utcnow()
    series = repository.get_series(session, series_id)
    if not series.is_active:
        raise ValidationFailed(f"Series {series.code} is inactive")
    _ensure_currency_unit(series, currency, unit)
    source = repository.get_source_by_code(session, source_code)
    _ensure_source_active(source)
    if source.source_type != SourceType.MANUAL:
        raise ValidationFailed(f"Source {source.code} does not accept manual benchmarks")
    reason = _require_reason(reason, "create a manual")
    resolved_from = effective_from or default_effective_from(source_as_of_date)
    _ensure_window(resolved_from, effective_until)
    _ensure_effective_free(session, series.id, resolved_from)

    benchmark = BenchmarkRate(
        series_id=series.id,
        primary_source_id=source.id,
        value=_normalise_price(value),
        currency=series.currency,
        unit=series.unit,
        price_basis=series.price_basis,
        tax_basis=series.tax_basis,
        method=BenchmarkMethod.MANUAL,
        origin=BenchmarkOrigin.HUMAN,
        is_edited=False,
        four_eyes_required=True,
        status=BenchmarkStatus.DRAFT,
        source_as_of_date=source_as_of_date,
        effective_from=resolved_from,
        effective_until=effective_until,
        reason=reason,
        evidence_ref=evidence_ref,
        created_by_id=actor.user_id,
        created_at=now,
        updated_at=now,
    )
    session.add(benchmark)
    session.flush()
    _record(
        session, entity_id=benchmark.id, action="created", actor_id=actor.user_id, now=now,
        to_status=BenchmarkStatus.DRAFT, reason=reason, changes={"mode": "manual", "value": str(benchmark.value)},
    )
    return benchmark


def edit_benchmark(
    session: Session,
    actor: Actor,
    benchmark_id: uuid.UUID,
    *,
    row_version: int,
    value: Decimal | None = None,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    source_rate_id: uuid.UUID | None = None,
    reason: str | None = None,
    evidence_ref: str | None = None,
    now: datetime | None = None,
) -> BenchmarkRate:
    """Edits a draft/submitted candidate. Any change to a four-eyes field marks it edited."""
    actor.require(PricingPermission.EDIT)
    now = now or utcnow()
    benchmark = repository.get_benchmark(session, benchmark_id, for_update=True)
    if benchmark.status in (BenchmarkStatus.PUBLISHED, BenchmarkStatus.WITHDRAWN):
        raise PublishedBenchmarkImmutable(
            "Published benchmarks cannot be changed; publish a new benchmark instead"
        )
    if benchmark.status == BenchmarkStatus.REJECTED:
        raise InvalidStateTransition("Rejected benchmarks cannot be edited")
    if benchmark.row_version != row_version:
        raise StaleRowVersion(
            "Benchmark was changed by someone else",
            details={"expected": row_version, "current": benchmark.row_version},
        )

    changes: dict[str, Any] = {}

    if source_rate_id is not None:
        current_input = repository.primary_input(benchmark)
        if current_input is None or current_input.source_rate_id != source_rate_id:
            source_rate = repository.get_source_rate(session, source_rate_id)
            validate_source_rate_for_series(session, source_rate, benchmark.series_id)
            if current_input is not None:
                benchmark.inputs.remove(current_input)
                session.flush()
            benchmark.inputs.append(
                BenchmarkRateInput(source_rate_id=source_rate.id, role=InputRole.PRIMARY)
            )
            changes["input"] = {
                "from": str(current_input.source_rate_id) if current_input else None,
                "to": str(source_rate.id),
            }
            benchmark.primary_source_id = source_rate.source_id
            if source_rate.source_as_of_date != benchmark.source_as_of_date:
                changes["sourceAsOfDate"] = {
                    "from": benchmark.source_as_of_date.isoformat(),
                    "to": source_rate.source_as_of_date.isoformat(),
                }
                benchmark.source_as_of_date = source_rate.source_as_of_date
                if effective_from is None:
                    effective_from = default_effective_from(source_rate.source_as_of_date)
            if value is None and source_rate.value != benchmark.value:
                changes["value"] = {"from": str(benchmark.value), "to": str(source_rate.value)}
                benchmark.value = source_rate.value

    if value is not None:
        new_value = _normalise_price(value)
        if new_value != benchmark.value:
            changes["value"] = {"from": str(benchmark.value), "to": str(new_value)}
            benchmark.value = new_value
            if benchmark.method == BenchmarkMethod.ADOPTED:
                benchmark.method = BenchmarkMethod.MANUAL
                changes["method"] = {"from": "adopted", "to": "manual"}

    if effective_from is not None and effective_from != benchmark.effective_from:
        _ensure_effective_free(session, benchmark.series_id, effective_from, exclude_id=benchmark.id)
        changes["effectiveFrom"] = {
            "from": benchmark.effective_from.isoformat(),
            "to": effective_from.isoformat(),
        }
        benchmark.effective_from = effective_from

    if effective_until is not None and effective_until != benchmark.effective_until:
        changes["effectiveUntil"] = {
            "from": benchmark.effective_until.isoformat() if benchmark.effective_until else None,
            "to": effective_until.isoformat(),
        }
        benchmark.effective_until = effective_until
    _ensure_window(benchmark.effective_from, benchmark.effective_until)

    if reason is not None and reason.strip() != (benchmark.reason or ""):
        benchmark.reason = reason.strip()
        changes["reason"] = True
    if evidence_ref is not None and evidence_ref != benchmark.evidence_ref:
        benchmark.evidence_ref = evidence_ref
        changes["evidenceRef"] = True

    if not changes:
        return benchmark
    if benchmark.method == BenchmarkMethod.MANUAL:
        _require_reason(benchmark.reason, "edit the value of")

    four_eyes_fields = {"input", "value", "effectiveFrom", "effectiveUntil", "sourceAsOfDate"}
    if four_eyes_fields & changes.keys():
        benchmark.is_edited = True
        benchmark.four_eyes_required = True
    benchmark.last_edited_by_id = actor.user_id
    benchmark.last_edited_at = now
    session.flush()
    _record(session, entity_id=benchmark.id, action="edited", actor_id=actor.user_id, now=now, changes=changes)
    return benchmark


def submit_benchmark(
    session: Session, actor: Actor, benchmark_id: uuid.UUID, *, now: datetime | None = None
) -> BenchmarkRate:
    actor.require(PricingPermission.EDIT)
    now = now or utcnow()
    benchmark = repository.get_benchmark(session, benchmark_id, for_update=True)
    previous = _transition(benchmark, BenchmarkStatus.SUBMITTED)
    benchmark.submitted_by_id = actor.user_id
    benchmark.submitted_at = now
    session.flush()
    _record(
        session, entity_id=benchmark.id, action="submitted", actor_id=actor.user_id, now=now,
        from_status=previous, to_status=BenchmarkStatus.SUBMITTED,
    )
    return benchmark


def _authors(session: Session, benchmark: BenchmarkRate) -> set[uuid.UUID]:
    return {benchmark.created_by_id} | repository.editor_ids(session, benchmark.id)


def publish_benchmark(
    session: Session, actor: Actor, benchmark_id: uuid.UUID, *, now: datetime | None = None
) -> BenchmarkRate:
    actor.require(PricingPermission.PUBLISH)
    now = now or utcnow()
    benchmark = repository.get_benchmark(session, benchmark_id, for_update=True)
    if benchmark.status != BenchmarkStatus.SUBMITTED:
        _transition(benchmark, BenchmarkStatus.PUBLISHED)  # raises with the precise from/to

    if benchmark.four_eyes_required and actor.user_id in _authors(session, benchmark):
        raise FourEyesRequired(
            "This benchmark was created or edited by you; a different publisher must publish it",
            details={"benchmarkId": str(benchmark.id)},
        )

    source = session.get(RateSource, benchmark.primary_source_id)
    _ensure_source_active(source)
    series = repository.get_series(session, benchmark.series_id)
    _ensure_currency_unit(series, benchmark.currency, benchmark.unit)
    primary = repository.primary_input(benchmark)
    if benchmark.method == BenchmarkMethod.ADOPTED:
        if primary is None:
            raise SourceRateUnresolved("Adopted benchmark has no source rate input")
    if primary is not None:
        validate_source_rate_for_series(
            session, repository.get_source_rate(session, primary.source_rate_id), benchmark.series_id
        )
    _ensure_window(benchmark.effective_from, benchmark.effective_until)
    _ensure_effective_free(session, benchmark.series_id, benchmark.effective_from, exclude_id=benchmark.id)

    previous = _transition(benchmark, BenchmarkStatus.PUBLISHED)
    benchmark.staleness_days = source.staleness_days
    benchmark.stale_after = compute_stale_after(benchmark.source_as_of_date, source.staleness_days)
    benchmark.published_by_id = actor.user_id
    benchmark.published_at = now
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise DuplicateEffectiveFrom(
            "A published benchmark already exists for this series at this effective date"
        ) from exc
    _record(
        session, entity_id=benchmark.id, action="published", actor_id=actor.user_id, now=now,
        from_status=previous, to_status=BenchmarkStatus.PUBLISHED,
        changes={"staleAfter": benchmark.stale_after.isoformat(), "stalenessDays": source.staleness_days},
    )
    return benchmark


def reject_benchmark(
    session: Session, actor: Actor, benchmark_id: uuid.UUID, *, reason: str, now: datetime | None = None
) -> BenchmarkRate:
    now = now or utcnow()
    benchmark = repository.get_benchmark(session, benchmark_id, for_update=True)
    own_draft = benchmark.status == BenchmarkStatus.DRAFT and benchmark.created_by_id == actor.user_id
    if not (actor.has(PricingPermission.PUBLISH) or (own_draft and actor.has(PricingPermission.EDIT))):
        raise PermissionDenied("Requires permission: pricing.publish", details={"required": ["pricing.publish"]})
    reason = _require_reason(reason, "reject")
    previous = _transition(benchmark, BenchmarkStatus.REJECTED)
    benchmark.rejected_by_id = actor.user_id
    benchmark.rejected_at = now
    benchmark.rejected_reason = reason
    session.flush()
    _record(
        session, entity_id=benchmark.id, action="rejected", actor_id=actor.user_id, now=now,
        from_status=previous, to_status=BenchmarkStatus.REJECTED, reason=reason,
    )
    return benchmark


def withdraw_benchmark(
    session: Session, actor: Actor, benchmark_id: uuid.UUID, *, reason: str, now: datetime | None = None
) -> BenchmarkRate:
    actor.require(PricingPermission.PUBLISH)
    now = now or utcnow()
    reason = _require_reason(reason, "withdraw")
    benchmark = repository.get_benchmark(session, benchmark_id, for_update=True)
    previous = _transition(benchmark, BenchmarkStatus.WITHDRAWN)
    benchmark.withdrawn_by_id = actor.user_id
    benchmark.withdrawn_at = now
    benchmark.withdrawn_reason = reason
    session.flush()
    _record(
        session, entity_id=benchmark.id, action="withdrawn", actor_id=actor.user_id, now=now,
        from_status=previous, to_status=BenchmarkStatus.WITHDRAWN, reason=reason,
    )
    return benchmark
