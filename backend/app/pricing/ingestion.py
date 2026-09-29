"""Ingestion of ERP price-list rows into source rates.

The row shape mirrors the ERP price list (DomesticPrice1). No ERP connection exists yet: callers
(the demo seed today, a real connector later) hand rows to `ingest_price_list`. All
source-specific interpretation lives in the source's versioned `normalization_profile`.
"""

import hashlib
import json
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue.resolver import resolve_grade, resolve_market, resolve_producer
from app.core.clock import utcnow
from app.core.errors import SourceInactive, ValidationFailed
from app.models.pricing import BenchmarkRate, ImportBatch, RateSource, SourceRate
from app.pricing import repository, service
from app.pricing.constants import (
    BENCHMARK_PRICE_FIELDS,
    ImportBatchStatus,
    ResolutionStatus,
    SUPPORTED_CURRENCIES,
    SUPPORTED_UNITS,
    SourceType,
)

EQUALITY_TOLERANCE = Decimal("0.0001")
PRICE_QUANTUM = Decimal("0.0001")


@dataclass
class NormalizedRow:
    identity_key: str
    identity_signature: str
    row_ref: str
    raw_producer: str | None
    raw_grade: str | None
    raw_location: str | None
    raw_sector: str | None
    application: str | None
    origin_location: str | None
    market_text: str | None
    sector: str | None = None
    currency: str | None = None
    unit: str | None = None
    value: Decimal | None = None
    benchmark_field: str | None = None
    price_basis: str | None = None
    tax_basis: str | None = None
    eligible: bool = False
    eligibility_reason: str | None = None
    error: str | None = None


@dataclass
class IngestResult:
    batch: ImportBatch
    source_rates: list[SourceRate] = field(default_factory=list)
    suggestions: list[BenchmarkRate] = field(default_factory=list)
    duplicate: bool = False


def _text(row: Mapping[str, Any], name: str | None) -> str | None:
    if not name:
        return None
    value = row.get(name)
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _decimal(value: Any) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _is_empty_component(value: Any) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    number = _decimal(value)
    return number is not None and number == 0


def normalize_erp_row(row: Mapping[str, Any], profile: Mapping[str, Any]) -> NormalizedRow:
    fields = profile["fields"]
    key = _text(row, profile["row_key_field"])
    raw_location = _text(row, fields["location"])
    identity_parts = [_text(row, fields[name]) or "" for name in profile["identity_fields"]]

    origin, market_text = raw_location, raw_location
    separator = profile.get("route_separator")
    if raw_location and separator and separator.lower() in raw_location.lower():
        idx = raw_location.lower().index(separator.lower())
        origin = raw_location[:idx].strip()
        destination = raw_location[idx + len(separator):].strip()
        market_text = destination if profile.get("route_market") == "destination" else origin

    normalized = NormalizedRow(
        identity_key=key or "",
        identity_signature="|".join(identity_parts),
        row_ref=f"{profile['table']}:{profile['row_key_field']}={key}",
        raw_producer=_text(row, fields["producer"]),
        raw_grade=_text(row, fields["grade"]),
        raw_location=raw_location,
        raw_sector=_text(row, fields["sector"]),
        application=_text(row, fields.get("application")),
        origin_location=origin,
        market_text=market_text,
    )
    if not key:
        normalized.error = "missing_row_key"
        return normalized

    sector_rule = profile["sectors"].get((normalized.raw_sector or "").upper())
    if sector_rule is None:
        normalized.error = "unknown_sector"
        return normalized
    normalized.sector = sector_rule["code"]
    normalized.price_basis = sector_rule["price_basis"]
    normalized.tax_basis = sector_rule["tax_basis"]
    normalized.eligible = bool(sector_rule["benchmark_eligible"])
    if not normalized.eligible:
        normalized.eligibility_reason = "sector_not_eligible"

    currency = (_text(row, fields["currency"]) or "").upper()
    if currency not in SUPPORTED_CURRENCIES:
        normalized.error = "unsupported_currency"
        return normalized
    normalized.currency = currency
    unit = profile["unit"]
    if unit not in SUPPORTED_UNITS:
        normalized.error = "unsupported_unit"
        return normalized
    normalized.unit = unit

    benchmark_field = profile.get("benchmark_field")
    if benchmark_field and benchmark_field not in BENCHMARK_PRICE_FIELDS:
        normalized.error = "invalid_benchmark_field"
        return normalized
    value_field = benchmark_field or profile["value_field"]
    normalized.benchmark_field = value_field
    value = _decimal(row.get(value_field))
    if value is None or value <= 0:
        normalized.error = "invalid_value"
        return normalized
    # A configured benchmark field is the only price used. The other three stay in the raw row.
    if not benchmark_field:
        for other in profile.get("must_equal_fields", []):
            other_value = _decimal(row.get(other))
            if other_value is None or abs(other_value - value) > EQUALITY_TOLERANCE:
                normalized.error = "price_fields_diverged"
                return normalized
    for component in profile.get("must_be_empty_fields", []):
        if not _is_empty_component(row.get(component)):
            normalized.error = "unexpected_components"
            return normalized
    normalized.value = value.quantize(PRICE_QUANTUM)
    return normalized


def _checksum(rows: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps(list(rows), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _json_safe(row: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(row), default=str))


def _build_source_rate(
    session: Session,
    *,
    source: RateSource,
    batch: ImportBatch,
    row: Mapping[str, Any],
    normalized: NormalizedRow,
    created_by_id: uuid.UUID,
    now: datetime,
) -> SourceRate:
    source_rate = SourceRate(
        source_id=source.id,
        import_batch_id=batch.id,
        source_row_ref=normalized.row_ref,
        source_row_key=f"{batch.source_as_of_date.isoformat()}:{normalized.identity_key}",
        source_identity_key=normalized.identity_key or "?",
        source_as_of_date=batch.source_as_of_date,
        raw_producer=normalized.raw_producer,
        raw_grade=normalized.raw_grade,
        raw_location=normalized.raw_location,
        raw_sector=normalized.raw_sector,
        origin_location=normalized.origin_location,
        application=normalized.application,
        sector=normalized.sector,
        value=normalized.value,
        currency=normalized.currency,
        unit=normalized.unit,
        price_basis=normalized.price_basis,
        tax_basis=normalized.tax_basis,
        raw_payload={
            "row": _json_safe(row),
            "identitySignature": normalized.identity_signature,
            "benchmarkField": normalized.benchmark_field,
        },
        normalization_profile_version=source.profile_version,
        resolution_status=ResolutionStatus.UNRESOLVED,
        is_benchmark_eligible=False,
        eligibility_reason=normalized.eligibility_reason,
        created_by_id=created_by_id,
        created_at=now,
    )

    def unresolved(reason: str) -> SourceRate:
        source_rate.resolution_status = ResolutionStatus.UNRESOLVED
        source_rate.resolution_reason = reason
        return source_rate

    if normalized.error:
        return unresolved(normalized.error)

    previous = repository.previous_source_rate(
        session, source_id=source.id, identity_key=normalized.identity_key, before=batch.source_as_of_date
    )
    if previous is not None:
        if previous.raw_payload.get("identitySignature") != normalized.identity_signature:
            return unresolved("row_identity_changed")
        source_rate.is_unchanged = (
            previous.value == normalized.value and previous.currency == normalized.currency
        )

    producer = resolve_producer(session, normalized.raw_producer)
    if producer is None:
        return unresolved("unknown_producer")
    source_rate.producer_id = producer.id
    grade = resolve_grade(session, producer.id, normalized.raw_grade)
    if grade is None:
        return unresolved("unknown_grade")
    source_rate.grade_id = grade.grade.id
    source_rate.producer_grade_alias_id = grade.alias.id
    source_rate.grade_equivalence_id = grade.equivalence.id
    market = resolve_market(session, normalized.market_text)
    if market is None:
        return unresolved("unknown_market")
    source_rate.market_id = market.market.id
    source_rate.market_alias_id = market.alias.id

    if normalized.eligible:
        series = repository.find_series(
            session,
            grade_id=grade.grade.id,
            market_id=market.market.id,
            price_basis=normalized.price_basis,
            tax_basis=normalized.tax_basis,
            currency=normalized.currency,
            unit=normalized.unit,
        )
        if series is None:
            return unresolved("no_series")
        source_rate.series_id = series.id
        source_rate.is_benchmark_eligible = True

    source_rate.resolution_status = ResolutionStatus.RESOLVED
    return source_rate


def ingest_price_list(
    session: Session,
    *,
    source_code: str,
    source_as_of_date: date,
    rows: Sequence[Mapping[str, Any]],
    triggered_by_id: uuid.UUID,
    notes: str | None = None,
    create_suggestions: bool = True,
    now: datetime | None = None,
) -> IngestResult:
    now = now or utcnow()
    source = repository.get_source_by_code(session, source_code)
    if not source.is_active:
        raise SourceInactive(f"Rate source {source.code} is inactive", details={"source": source.code})
    if source.source_type not in (SourceType.ERP_FEED, SourceType.EXTERNAL_API):
        raise ValidationFailed(f"Source {source.code} does not accept imported price lists")

    checksum = _checksum(rows)
    existing = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_id == source.id,
            ImportBatch.source_as_of_date == source_as_of_date,
            ImportBatch.checksum == checksum,
        )
    )
    if existing is not None:
        return IngestResult(batch=existing, duplicate=True)

    batch = ImportBatch(
        source_id=source.id,
        source_as_of_date=source_as_of_date,
        status=ImportBatchStatus.RUNNING,
        triggered_by_id=triggered_by_id,
        started_at=now,
        checksum=checksum,
        row_count=len(rows),
        notes=notes,
    )
    session.add(batch)
    session.flush()

    result = IngestResult(batch=batch)
    for row in rows:
        normalized = normalize_erp_row(row, source.normalization_profile)
        source_rate = _build_source_rate(
            session, source=source, batch=batch, row=row, normalized=normalized,
            created_by_id=triggered_by_id, now=now,
        )
        session.add(source_rate)
        result.source_rates.append(source_rate)
    session.flush()

    batch.resolved_count = sum(r.resolution_status == ResolutionStatus.RESOLVED for r in result.source_rates)
    batch.unresolved_count = sum(r.resolution_status == ResolutionStatus.UNRESOLVED for r in result.source_rates)
    batch.ineligible_count = sum(
        r.resolution_status == ResolutionStatus.RESOLVED and not r.is_benchmark_eligible
        for r in result.source_rates
    )

    if create_suggestions:
        by_series: dict[uuid.UUID, list[SourceRate]] = defaultdict(list)
        for source_rate in result.source_rates:
            if source_rate.is_benchmark_eligible:
                by_series[source_rate.series_id].append(source_rate)
        for candidates in by_series.values():
            # Several producers for one series need an admin choice; unchanged re-entries add no point.
            if len(candidates) == 1 and not candidates[0].is_unchanged:
                suggestion = service.create_system_suggestion(
                    session, source_rate=candidates[0], system_user_id=triggered_by_id, now=now
                )
                if suggestion is not None:
                    result.suggestions.append(suggestion)

    batch.status = ImportBatchStatus.SUCCEEDED
    batch.finished_at = utcnow()
    session.flush()
    return result
