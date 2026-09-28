import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFound
from app.models.identity import User
from app.models.pricing import (
    BenchmarkRate,
    BenchmarkRateInput,
    PricingAuditEvent,
    RateSeries,
    RateSource,
    SourceRate,
)
from app.pricing.constants import TIMELINE_STATUSES


def get_source_by_code(session: Session, code: str) -> RateSource:
    source = session.scalar(select(RateSource).where(RateSource.code == code))
    if source is None:
        raise NotFound(f"Rate source {code!r} not found")
    return source


def get_series(session: Session, series_id: uuid.UUID) -> RateSeries:
    series = session.get(RateSeries, series_id)
    if series is None:
        raise NotFound("Rate series not found", details={"seriesId": str(series_id)})
    return series


def get_series_by_code(session: Session, code: str) -> RateSeries:
    series = session.scalar(select(RateSeries).where(RateSeries.code == code))
    if series is None:
        raise NotFound(f"Rate series {code!r} not found")
    return series


def find_series(
    session: Session,
    *,
    grade_id: uuid.UUID,
    market_id: uuid.UUID,
    price_basis: str,
    tax_basis: str,
    currency: str,
    unit: str,
) -> RateSeries | None:
    return session.scalar(
        select(RateSeries).where(
            RateSeries.grade_id == grade_id,
            RateSeries.market_id == market_id,
            RateSeries.price_basis == price_basis,
            RateSeries.tax_basis == tax_basis,
            RateSeries.currency == currency,
            RateSeries.unit == unit,
            RateSeries.is_active.is_(True),
        )
    )


def get_source_rate(session: Session, source_rate_id: uuid.UUID) -> SourceRate:
    source_rate = session.get(SourceRate, source_rate_id)
    if source_rate is None:
        raise NotFound("Source rate not found", details={"sourceRateId": str(source_rate_id)})
    return source_rate


def previous_source_rate(
    session: Session, *, source_id: uuid.UUID, identity_key: str, before: date
) -> SourceRate | None:
    return session.scalar(
        select(SourceRate)
        .where(
            SourceRate.source_id == source_id,
            SourceRate.source_identity_key == identity_key,
            SourceRate.source_as_of_date < before,
        )
        .order_by(SourceRate.source_as_of_date.desc())
        .limit(1)
    )


def get_benchmark(session: Session, benchmark_id: uuid.UUID, *, for_update: bool = False) -> BenchmarkRate:
    stmt = (
        select(BenchmarkRate)
        .where(BenchmarkRate.id == benchmark_id)
        .options(selectinload(BenchmarkRate.inputs))
    )
    if for_update:
        stmt = stmt.with_for_update()
    benchmark = session.scalar(stmt)
    if benchmark is None:
        raise NotFound("Benchmark not found", details={"benchmarkId": str(benchmark_id)})
    return benchmark


def primary_input(benchmark: BenchmarkRate) -> BenchmarkRateInput | None:
    return next((i for i in benchmark.inputs if i.role == "primary"), None)


def effective_from_taken(
    session: Session,
    *,
    series_id: uuid.UUID,
    effective_from: datetime,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    stmt = select(BenchmarkRate.id).where(
        BenchmarkRate.series_id == series_id,
        BenchmarkRate.effective_from == effective_from,
        BenchmarkRate.status.in_(TIMELINE_STATUSES),
    )
    if exclude_id is not None:
        stmt = stmt.where(BenchmarkRate.id != exclude_id)
    return session.scalar(stmt.limit(1)) is not None


def editor_ids(session: Session, benchmark_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        session.scalars(
            select(PricingAuditEvent.actor_id).where(
                PricingAuditEvent.entity_type == "benchmark_rate",
                PricingAuditEvent.entity_id == benchmark_id,
                PricingAuditEvent.action == "edited",
            )
        )
    )


def timelines(session: Session, series_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[BenchmarkRate]]:
    ids = list(series_ids)
    result: dict[uuid.UUID, list[BenchmarkRate]] = defaultdict(list)
    if not ids:
        return result
    rows = session.scalars(
        select(BenchmarkRate)
        .where(BenchmarkRate.series_id.in_(ids), BenchmarkRate.status.in_(TIMELINE_STATUSES))
        .order_by(BenchmarkRate.effective_from)
    )
    for row in rows:
        result[row.series_id].append(row)
    return result


def user_emails(session: Session, user_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = session.execute(select(User.id, User.email).where(User.id.in_(ids)))
    return {user_id: email for user_id, email in rows}


def audit_events(
    session: Session, *, entity_type: str | None = None, entity_id: uuid.UUID | None = None, limit: int = 200
) -> Sequence[PricingAuditEvent]:
    stmt = select(PricingAuditEvent).order_by(PricingAuditEvent.occurred_at.desc()).limit(limit)
    if entity_type:
        stmt = stmt.where(PricingAuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(PricingAuditEvent.entity_id == entity_id)
    return session.scalars(stmt).all()
