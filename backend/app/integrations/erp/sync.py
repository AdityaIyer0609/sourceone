"""ERP -> SourceOne sync: read (ERP), validate, then store in SourceOne PostgreSQL only.

Prices go through the existing ingestion pipeline unchanged, so imported rows become source rates
and, at most, benchmark suggestions awaiting admin review. Nothing is published here, and nothing
is ever sent to the ERP.
"""

import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalogue.resolver import normalize_text, resolve_grade, resolve_producer
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import ErpNotConfigured, ErpSyncInProgress
from app.identity.service import Actor
from app.integrations.erp.constants import (
    GSTIN_PATTERN,
    PIN_PATTERN,
    PRICE_COLUMNS,
    GradeMappingStatus,
    IntegrationPermission,
    SyncRunStatus,
)
from app.integrations.erp.reader import ErpReader, ErpRow
from app.models.erp import ErpCustomer, ErpGrade, ErpPriceRowImport, ErpSyncRun
from app.models.identity import User
from app.models.pricing import BenchmarkRate, BenchmarkRateInput, ImportBatch, RateSource, SourceRate
from app.pricing import ingestion
from app.pricing.constants import BenchmarkStatus, ResolutionStatus
from app.schemas.erp import (
    CustomerSyncStats,
    ErpGradeRef,
    ErpSyncStats,
    GradeSyncStats,
    PriceSyncStats,
    RejectedPriceRow,
    SyncWarning,
    UnresolvedGrade,
)

SYNC_LOCK_KEY = 0x45525053  # "ERPS": one ERP sync at a time across all API workers
GRADE_REASONS = ("unknown_producer", "unknown_grade")
REJECTED_ROWS_REPORTED = 100


def _text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _decimal(value: Any) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _sr_no(value: Any) -> int | None:
    number = _decimal(value)
    if number is None or number != number.to_integral_value() or number <= 0:
        return None
    return int(number)


def _sys_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None, second=0, microsecond=0)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str) and value.strip():
        try:
            return _sys_date(datetime.fromisoformat(value.strip()))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------------------------- prices


@dataclass
class PreparedPrices:
    snapshot_sys_date: datetime | None = None
    rows: dict[int, tuple[datetime, dict[str, Any]]] = field(default_factory=dict)
    rejected: list[RejectedPriceRow] = field(default_factory=list)

    @property
    def as_of_date(self) -> date | None:
        return self.snapshot_sys_date.date() if self.snapshot_sys_date else None


def prepare_price_rows(raw_rows: Sequence[ErpRow]) -> PreparedPrices:
    """Validate row identity (SysDate + SrNo) and keep only the latest price date."""
    prepared = PreparedPrices()
    parsed: list[tuple[int, datetime, ErpRow]] = []
    for raw in raw_rows:
        sr_no, sys_date = _sr_no(raw.get("SrNo")), _sys_date(raw.get("SysDate"))
        reason = (
            ("missing_sr_no" if _text(raw.get("SrNo")) is None else "invalid_sr_no") if sr_no is None
            else ("missing_sys_date" if _text(raw.get("SysDate")) is None else "invalid_sys_date") if sys_date is None
            else None
        )
        if reason:
            prepared.rejected.append(RejectedPriceRow(sr_no=sr_no, sys_date=sys_date, reason=reason))
            continue
        parsed.append((sr_no, sys_date, raw))
    if not parsed:
        return prepared

    prepared.snapshot_sys_date = max(sys_date for _, sys_date, _ in parsed)
    snapshot_day = prepared.snapshot_sys_date.date()
    by_sr_no: dict[int, list[tuple[datetime, ErpRow]]] = defaultdict(list)
    for sr_no, sys_date, raw in parsed:
        if sys_date.date() != snapshot_day:
            prepared.rejected.append(RejectedPriceRow(sr_no=sr_no, sys_date=sys_date, reason="outside_latest_snapshot"))
            continue
        by_sr_no[sr_no].append((sys_date, raw))

    for sr_no, entries in sorted(by_sr_no.items()):
        entries.sort(key=lambda entry: entry[0], reverse=True)
        (sys_date, raw), *others = entries
        for other_date, _ in others:
            reason = "duplicate_row" if other_date == sys_date else "superseded_in_snapshot"
            prepared.rejected.append(RejectedPriceRow(sr_no=sr_no, sys_date=other_date, reason=reason))
        row = {column: raw.get(column) for column in PRICE_COLUMNS}
        row["SrNo"] = sr_no
        row["SysDate"] = sys_date.isoformat(timespec="minutes")
        prepared.rows[sr_no] = (sys_date, row)
    return prepared


def _already_imported(session: Session, source: RateSource, day: date) -> set[tuple[datetime, int]]:
    start = datetime(day.year, day.month, day.day)
    rows = session.execute(
        select(ErpPriceRowImport.erp_sys_date, ErpPriceRowImport.erp_sr_no).where(
            ErpPriceRowImport.source_id == source.id,
            ErpPriceRowImport.erp_sys_date >= start,
            ErpPriceRowImport.erp_sys_date < start + timedelta(days=1),
        )
    ).all()
    return {(sys_date, sr_no) for sys_date, sr_no in rows}


def _published_from(session: Session, batch: ImportBatch) -> int:
    return session.scalar(
        select(func.count(func.distinct(BenchmarkRate.id)))
        .join(BenchmarkRateInput, BenchmarkRateInput.benchmark_rate_id == BenchmarkRate.id)
        .join(SourceRate, SourceRate.id == BenchmarkRateInput.source_rate_id)
        .where(SourceRate.import_batch_id == batch.id, BenchmarkRate.status == BenchmarkStatus.PUBLISHED)
    ) or 0


def _price_grade_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (normalize_text(_text(row.get("Company"))), normalize_text(_text(row.get("Quality"))),
            normalize_text(_text(row.get("Grade"))))


def _rate_grade_key(rate: SourceRate) -> tuple[str, str, str]:
    quality = (rate.raw_payload or {}).get("row", {}).get("Quality")
    return (normalize_text(rate.raw_producer), normalize_text(_text(quality)), normalize_text(rate.raw_grade))


def _unresolved_grades(
    source_rates: Sequence[SourceRate], grades: Mapping[tuple[str, str, str], ErpGrade]
) -> list[UnresolvedGrade]:
    """Grades the catalogue does not already map. Nothing here creates a producer or grade mapping."""
    groups: dict[tuple[str, str, str, str], list[SourceRate]] = defaultdict(list)
    for rate in source_rates:
        if rate.resolution_reason in GRADE_REASONS:
            company_key, quality_key, grade_key = _rate_grade_key(rate)
            groups[(company_key, quality_key, grade_key, rate.resolution_reason)].append(rate)
    report = []
    for (company_key, quality_key, grade_key, reason), rates in sorted(groups.items()):
        reference = grades.get((company_key, quality_key, grade_key))
        report.append(UnresolvedGrade(
            company=rates[0].raw_producer,
            quality=_text((rates[0].raw_payload or {}).get("row", {}).get("Quality")),
            grade=rates[0].raw_grade,
            reason=reason,
            row_count=len(rates),
            sr_nos=sorted(int(r.source_identity_key) for r in rates),
            erp_grade_master=ErpGradeRef(
                found=reference is not None,
                mapping_status=reference.mapping_status if reference else None,
                erp_item_code=reference.erp_item_code if reference else None,
            ),
        ))
    return report


def _snapshot_rates(session: Session, source: RateSource, prepared: PreparedPrices) -> list[SourceRate]:
    """Source rates already stored for this snapshot, so a repeat sync still reports unresolved grades."""
    if not prepared.rows:
        return []
    wanted = {(sys_date, sr_no) for sr_no, (sys_date, _) in prepared.rows.items()}
    rows = session.execute(
        select(SourceRate, ErpPriceRowImport.erp_sys_date, ErpPriceRowImport.erp_sr_no)
        .join(ErpPriceRowImport, ErpPriceRowImport.source_rate_id == SourceRate.id)
        .where(ErpPriceRowImport.source_id == source.id)
    ).all()
    return [rate for rate, sys_date, sr_no in rows if (sys_date, sr_no) in wanted]


def _sync_prices(
    session: Session, run: ErpSyncRun, source: RateSource, system_user_id: uuid.UUID,
    raw_rows: Sequence[ErpRow], now: datetime,
) -> tuple[PriceSyncStats, ImportBatch | None, list[SourceRate]]:
    stats = PriceSyncStats(rows_read=len(raw_rows))
    prepared = prepare_price_rows(raw_rows)
    stats.rejected, stats.rejected_rows = len(prepared.rejected), prepared.rejected[:REJECTED_ROWS_REPORTED]
    run.snapshot_sys_date, run.snapshot_as_of_date = prepared.snapshot_sys_date, prepared.as_of_date
    if not prepared.rows:
        return stats, None, []

    done = _already_imported(session, source, prepared.as_of_date)
    new = {sr_no: entry for sr_no, entry in prepared.rows.items() if (entry[0], sr_no) not in done}
    stats.already_imported = len(prepared.rows) - len(new)
    stats.skipped = stats.already_imported
    if not new:
        return stats, None, []

    result = ingestion.ingest_price_list(
        session,
        source_code=source.code,
        source_as_of_date=prepared.as_of_date,
        rows=[row for _, row in new.values()],
        triggered_by_id=system_user_id,
        notes=f"ERP read-only sync {run.id}: DomesticPrice1 snapshot {prepared.snapshot_sys_date.isoformat()}",
        now=now,
    )
    if result.duplicate:
        stats.already_imported += len(new)
        stats.skipped = stats.already_imported
        return stats, result.batch, []

    for rate in result.source_rates:
        sr_no = int(rate.source_identity_key)
        session.add(ErpPriceRowImport(
            source_id=source.id, erp_sys_date=new[sr_no][0], erp_sr_no=sr_no,
            source_rate_id=rate.id, sync_run_id=run.id, created_at=now,
        ))
    session.flush()

    batch = result.batch
    stats.imported = len(result.source_rates)
    stats.resolved, stats.unresolved, stats.ineligible = (
        batch.resolved_count, batch.unresolved_count, batch.ineligible_count
    )
    stats.flagged_by_reason = dict(sorted(Counter(
        r.resolution_reason for r in result.source_rates
        if r.resolution_status == ResolutionStatus.UNRESOLVED and r.resolution_reason
    ).items()))
    stats.suggestions_submitted_for_review = len(result.suggestions)
    stats.benchmarks_published = _published_from(session, batch)
    return stats, batch, result.source_rates


# ---------------------------------------------------------------------------------------------- grades


def _grade_mapping(session: Session, company: str, grade: str) -> tuple[str, uuid.UUID | None, uuid.UUID | None]:
    producer = resolve_producer(session, company)
    if producer is None:
        return GradeMappingStatus.UNMAPPED_PRODUCER, None, None
    resolution = resolve_grade(session, producer.id, grade)
    if resolution is None:
        return GradeMappingStatus.UNMAPPED_GRADE, producer.id, None
    return GradeMappingStatus.MAPPED, producer.id, resolution.alias.id


def _sync_grades(
    session: Session, run: ErpSyncRun, raw_rows: Sequence[ErpRow], now: datetime
) -> tuple[GradeSyncStats, dict[tuple[str, str, str], ErpGrade]]:
    """Identity is Company + Quality + Grade. An existing catalogue alias may match; none is created."""
    stats = GradeSyncStats(rows_read=len(raw_rows))
    existing = {
        (g.company_normalized, g.quality_normalized, g.grade_normalized): g
        for g in session.scalars(select(ErpGrade))
    }
    seen: dict[tuple[str, str, str], ErpGrade] = {}
    for raw in raw_rows:
        company, quality, grade = _text(raw.get("Company")), _text(raw.get("Quality")) or "", _text(raw.get("Grade"))
        if not company or not grade or len(company) > 128 or len(grade) > 128 or len(quality) > 64:
            stats.rejected += 1
            continue
        key = (normalize_text(company), normalize_text(quality), normalize_text(grade))
        if key in seen:
            stats.rejected += 1
            continue
        status, producer_id, alias_id = _grade_mapping(session, company, grade)
        values = {
            "company": company, "quality": quality or None, "quality_normalized": key[1], "grade": grade,
            "erp_sr_no": _sr_no(raw.get("SrNo")), "mfi": _decimal(raw.get("MFI")),
            "density": _decimal(raw.get("Density")), "erp_item_code": (_text(raw.get("ItemCode")) or "")[:64] or None,
            "producer_id": producer_id, "producer_grade_alias_id": alias_id, "mapping_status": status,
        }
        record = existing.get(key)
        if record is None:
            record = ErpGrade(
                company_normalized=key[0], grade_normalized=key[2], first_seen_at=now, **values
            )
            session.add(record)
            stats.created += 1
        elif any(getattr(record, name) != value for name, value in values.items()):
            for name, value in values.items():
                setattr(record, name, value)
            stats.updated += 1
        else:
            stats.unchanged += 1
        record.last_synced_at, record.last_sync_run_id = now, run.id
        seen[key] = record
        stats.mapped += status == GradeMappingStatus.MAPPED
        stats.unmapped_producer += status == GradeMappingStatus.UNMAPPED_PRODUCER
        stats.unmapped_grade += status == GradeMappingStatus.UNMAPPED_GRADE
    session.flush()
    return stats, {**existing, **seen}


# ---------------------------------------------------------------------------------------------- customers


def _identity_code(value: Any, pattern: str) -> tuple[str | None, str]:
    """Returns (value or None, 'ok' | 'missing' | 'invalid')."""
    if isinstance(value, Decimal) and value == value.to_integral_value():
        value = str(int(value))
    code = re.sub(r"\s+", "", str(value or "")).upper()
    if not code:
        return None, "missing"
    return (code, "ok") if re.fullmatch(pattern, code) else (None, "invalid")


def _sync_customers(session: Session, run: ErpSyncRun, raw_rows: Sequence[ErpRow], now: datetime) -> CustomerSyncStats:
    stats = CustomerSyncStats(rows_read=len(raw_rows))
    names = {_text(raw.get("CompanyName")) for raw in raw_rows} - {None}
    existing = {c.erp_name: c for c in session.scalars(select(ErpCustomer).where(ErpCustomer.erp_name.in_(names)))}
    seen: set[str] = set()
    for raw in raw_rows:
        name = _text(raw.get("CompanyName"))
        if not name or len(name) > 255 or name in seen:
            stats.rejected += 1
            continue
        seen.add(name)
        gstin, gstin_state = _identity_code(raw.get("GSTIN"), GSTIN_PATTERN)
        pin, pin_state = _identity_code(raw.get("PINCode"), PIN_PATTERN)
        stats.missing_gstin += gstin_state == "missing"
        stats.invalid_gstin += gstin_state == "invalid"
        stats.missing_pin += pin_state == "missing"
        stats.invalid_pin += pin_state == "invalid"
        record = existing.get(name)
        if record is None:
            record = ErpCustomer(erp_name=name, gstin=gstin, pin_code=pin, first_seen_at=now)
            session.add(record)
            stats.created += 1
        elif (record.gstin, record.pin_code) != (gstin, pin):
            record.gstin, record.pin_code = gstin, pin
            stats.updated += 1
        else:
            stats.unchanged += 1
        record.last_synced_at, record.last_sync_run_id = now, run.id
    session.flush()
    return stats


WARNING_TEXT = {
    "invalid_value": "UnitPrice is missing or not a positive number",
    "price_fields_diverged": "Basic, Total or GrandTotal does not equal UnitPrice",
    "unexpected_components": "A discount, freight, GST amount or quantity slab is present",
    "unknown_sector": "Sector is not Domestic, Deemed or Import",
    "unsupported_currency": "Currency is not INR or USD",
    "unknown_producer": "Company is not an existing SourceOne producer; no mapping was created",
    "unknown_grade": "Company + Grade is not an existing SourceOne grade alias; no mapping was created",
    "grade_not_in_domestic_grade": "Company + Quality + Grade is not in DomesticGrade",
    "invalid_customer_identity": "Customer GSTIN or PIN is missing or not a valid code; the value was not stored",
}


def _warnings(
    price_rows: Sequence[ErpRow], rates: Sequence[SourceRate], grade_stats: GradeSyncStats,
    customer_stats: CustomerSyncStats, grades: Mapping[tuple[str, str, str], ErpGrade],
) -> list[SyncWarning]:
    reasons = Counter(
        rate.resolution_reason for rate in rates
        if rate.resolution_status == ResolutionStatus.UNRESOLVED and rate.resolution_reason
    )
    warnings = [
        SyncWarning(code=reason, count=count, message=WARNING_TEXT.get(reason, reason))
        for reason, count in sorted(reasons.items())
    ]
    missing = sum(1 for _, row in prepare_price_rows(price_rows).rows.values() if _price_grade_key(row) not in grades)
    if missing:
        warnings.append(SyncWarning(
            code="grade_not_in_domestic_grade", count=missing, message=WARNING_TEXT["grade_not_in_domestic_grade"],
        ))
    if grade_stats.rejected:
        warnings.append(SyncWarning(
            code="invalid_grade_row", count=grade_stats.rejected,
            message="DomesticGrade row is missing Company or Grade, or repeats Company + Quality + Grade",
        ))
    identity_gaps = (
        customer_stats.missing_gstin + customer_stats.invalid_gstin
        + customer_stats.missing_pin + customer_stats.invalid_pin
    )
    if identity_gaps:
        warnings.append(SyncWarning(
            code="invalid_customer_identity", count=identity_gaps, message=WARNING_TEXT["invalid_customer_identity"],
        ))
    return warnings


# ---------------------------------------------------------------------------------------------- run


def run_sync(session: Session, actor: Actor, reader: ErpReader, *, now: datetime | None = None) -> ErpSyncRun:
    actor.require(IntegrationPermission.ERP_SYNC)
    now = now or utcnow()
    if not session.scalar(select(func.pg_try_advisory_xact_lock(SYNC_LOCK_KEY))):
        raise ErpSyncInProgress("Another ERP sync is running; try again shortly")

    source_code = get_settings().erp_rate_source_code
    source = session.scalar(select(RateSource).where(RateSource.code == source_code))
    if source is None:
        raise ErpNotConfigured("The ERP rate source is not configured in SourceOne", details={"sourceCode": source_code})
    system_user_id = session.scalar(
        select(User.id).where(User.is_system.is_(True), User.is_active.is_(True)).order_by(User.created_at).limit(1)
    )
    if system_user_id is None:
        raise ErpNotConfigured("No active SourceOne system user exists to own imported rows")

    # Read everything first: if the ERP fails part-way, SourceOne stores nothing from this run.
    grade_rows = reader.domestic_grades()
    customer_rows = reader.customers()
    price_rows = reader.latest_price_snapshot()

    run = ErpSyncRun(
        triggered_by_user_id=actor.user_id, adapter=reader.name, status=SyncRunStatus.SUCCEEDED, started_at=now,
    )
    session.add(run)
    session.flush()

    grade_stats, grades = _sync_grades(session, run, grade_rows, now)
    customer_stats = _sync_customers(session, run, customer_rows, now)
    price_stats, batch, _fresh = _sync_prices(session, run, source, system_user_id, price_rows, now)
    reported = _snapshot_rates(session, source, prepare_price_rows(price_rows))

    run.import_batch_id = batch.id if batch else None
    run.stats = ErpSyncStats(
        rows_read=price_stats.rows_read,
        imported=price_stats.imported,
        skipped=price_stats.skipped,
        rejected=price_stats.rejected,
        warnings=_warnings(price_rows, reported, grade_stats, customer_stats, grades),
        prices=price_stats,
        grades=grade_stats,
        customers=customer_stats,
        unresolved_grades=_unresolved_grades(reported, grades),
    ).model_dump(mode="json", by_alias=True)
    run.finished_at = utcnow()
    session.flush()
    return run
