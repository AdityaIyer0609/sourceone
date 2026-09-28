"""Pricing administration endpoints.

Buyers and suppliers also hold pricing.view, so reads here (which expose producers and source
rates) require an administrative pricing permission instead.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, require_any
from app.api.v1 import pricing_presenters as present
from app.core.clock import utcnow
from app.core.errors import ValidationFailed
from app.identity.service import Actor
from app.models.pricing import BenchmarkRate, BenchmarkRateInput, RateSeries, RateSource, SourceRate
from app.pricing import repository, service
from app.pricing.constants import PricingPermission
from app.schemas import pricing as schemas

router = APIRouter(prefix="/admin/pricing", tags=["admin-pricing"])

PricingAdmin = Annotated[
    Actor,
    Depends(require_any(PricingPermission.EDIT, PricingPermission.PUBLISH, PricingPermission.CONFIGURE)),
]
Editor = Annotated[Actor, Depends(require_any(PricingPermission.EDIT))]
Publisher = Annotated[Actor, Depends(require_any(PricingPermission.PUBLISH))]
AnyEditorOrPublisher = Annotated[
    Actor, Depends(require_any(PricingPermission.EDIT, PricingPermission.PUBLISH))
]


def _benchmark_query():
    return select(BenchmarkRate).options(
        selectinload(BenchmarkRate.series),
        selectinload(BenchmarkRate.inputs).selectinload(BenchmarkRateInput.source_rate),
    )


def _one(db: DbSession, benchmark_id: uuid.UUID) -> schemas.BenchmarkAdminOut:
    db.expire_all()
    benchmark = db.scalar(_benchmark_query().where(BenchmarkRate.id == benchmark_id))
    return present.benchmark_admin(db, [benchmark])[0]


@router.get("/sources", response_model=list[schemas.RateSourceOut])
def list_sources(db: DbSession, _: PricingAdmin):
    rows = db.scalars(select(RateSource).order_by(RateSource.priority, RateSource.code)).all()
    return [
        schemas.RateSourceOut(
            id=r.id, code=r.code, name=r.name, source_type=r.source_type, is_active=r.is_active,
            priority=r.priority, staleness_days=r.staleness_days, publishing_policy=r.publishing_policy,
            profile_version=r.profile_version,
        )
        for r in rows
    ]


@router.get("/source-rates", response_model=list[schemas.SourceRateOut])
def list_source_rates(
    db: DbSession,
    _: PricingAdmin,
    series_id: Annotated[uuid.UUID | None, Query(alias="seriesId")] = None,
    batch_id: Annotated[uuid.UUID | None, Query(alias="batchId")] = None,
    resolution_status: Annotated[str | None, Query(alias="resolutionStatus")] = None,
    sector: str | None = None,
    eligible: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    stmt = (
        select(SourceRate)
        .options(selectinload(SourceRate.source), selectinload(SourceRate.series))
        .order_by(SourceRate.source_as_of_date.desc(), SourceRate.source_row_ref)
        .limit(limit)
        .offset(offset)
    )
    if series_id:
        stmt = stmt.where(SourceRate.series_id == series_id)
    if batch_id:
        stmt = stmt.where(SourceRate.import_batch_id == batch_id)
    if resolution_status:
        stmt = stmt.where(SourceRate.resolution_status == resolution_status)
    if sector:
        stmt = stmt.where(SourceRate.sector == sector.upper())
    if eligible is not None:
        stmt = stmt.where(SourceRate.is_benchmark_eligible.is_(eligible))
    return [present.source_rate(db, row) for row in db.scalars(stmt).all()]


@router.get("/series", response_model=list[schemas.RateSeriesOut])
def list_series(db: DbSession, _: PricingAdmin):
    series_list = db.scalars(
        select(RateSeries)
        .options(selectinload(RateSeries.grade), selectinload(RateSeries.market))
        .order_by(RateSeries.display_order, RateSeries.code)
    ).all()
    timelines = repository.timelines(db, [s.id for s in series_list])
    now = utcnow()
    return [present.series_admin(s, timelines.get(s.id, []), now) for s in series_list]


@router.get("/series/{series_id}/timeline", response_model=schemas.SeriesTimelineOut)
def series_timeline(series_id: uuid.UUID, db: DbSession, _: PricingAdmin):
    """Full admin history of a series: every status, including rejected and withdrawn."""
    series = repository.get_series(db, series_id)
    benchmarks = db.scalars(
        _benchmark_query()
        .where(BenchmarkRate.series_id == series_id)
        .order_by(BenchmarkRate.effective_from.desc(), BenchmarkRate.created_at.desc())
    ).all()
    timeline = repository.timelines(db, [series.id]).get(series.id, [])
    return schemas.SeriesTimelineOut(
        series=present.series_admin(series, timeline, utcnow()),
        benchmarks=present.benchmark_admin(db, list(benchmarks)),
    )


@router.get("/benchmarks", response_model=list[schemas.BenchmarkAdminOut])
def list_benchmarks(
    db: DbSession,
    _: PricingAdmin,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    series_id: Annotated[uuid.UUID | None, Query(alias="seriesId")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    stmt = _benchmark_query().order_by(BenchmarkRate.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(BenchmarkRate.status == status_filter)
    if series_id:
        stmt = stmt.where(BenchmarkRate.series_id == series_id)
    return present.benchmark_admin(db, list(db.scalars(stmt).all()))


@router.get("/benchmarks/{benchmark_id}", response_model=schemas.BenchmarkAdminOut)
def get_benchmark(benchmark_id: uuid.UUID, db: DbSession, _: PricingAdmin):
    repository.get_benchmark(db, benchmark_id)
    return _one(db, benchmark_id)


@router.post("/benchmarks", response_model=schemas.BenchmarkAdminOut, status_code=status.HTTP_201_CREATED)
def create_benchmark(body: schemas.CreateBenchmarkIn, db: DbSession, actor: Editor):
    if body.mode == "select_source_rate":
        if body.source_rate_id is None:
            raise ValidationFailed("sourceRateId is required when selecting a source rate")
        benchmark = service.select_source_rate(
            db, actor,
            source_rate_id=body.source_rate_id,
            series_id=body.series_id,
            effective_from=body.effective_from,
            effective_until=body.effective_until,
        )
    else:
        missing = [
            name for name, value in (
                ("seriesId", body.series_id), ("value", body.value), ("currency", body.currency),
                ("unit", body.unit), ("sourceAsOfDate", body.source_as_of_date), ("reason", body.reason),
            ) if value is None
        ]
        if missing:
            raise ValidationFailed("Missing fields for a manual benchmark", details={"missing": missing})
        benchmark = service.create_manual_benchmark(
            db, actor,
            series_id=body.series_id,
            value=body.value,
            currency=body.currency.upper(),
            unit=body.unit.upper(),
            source_as_of_date=body.source_as_of_date,
            reason=body.reason,
            evidence_ref=body.evidence_ref,
            effective_from=body.effective_from,
            effective_until=body.effective_until,
        )
    db.commit()
    return _one(db, benchmark.id)


@router.patch("/benchmarks/{benchmark_id}", response_model=schemas.BenchmarkAdminOut)
def edit_benchmark(benchmark_id: uuid.UUID, body: schemas.EditBenchmarkIn, db: DbSession, actor: Editor):
    service.edit_benchmark(
        db, actor, benchmark_id,
        row_version=body.row_version,
        value=body.value,
        effective_from=body.effective_from,
        effective_until=body.effective_until,
        source_rate_id=body.source_rate_id,
        reason=body.reason,
        evidence_ref=body.evidence_ref,
    )
    db.commit()
    return _one(db, benchmark_id)


@router.post("/benchmarks/{benchmark_id}/submit", response_model=schemas.BenchmarkAdminOut)
def submit_benchmark(benchmark_id: uuid.UUID, db: DbSession, actor: Editor):
    service.submit_benchmark(db, actor, benchmark_id)
    db.commit()
    return _one(db, benchmark_id)


@router.post("/benchmarks/{benchmark_id}/publish", response_model=schemas.BenchmarkAdminOut)
def publish_benchmark(benchmark_id: uuid.UUID, db: DbSession, actor: Publisher):
    service.publish_benchmark(db, actor, benchmark_id)
    db.commit()
    return _one(db, benchmark_id)


@router.post("/benchmarks/{benchmark_id}/reject", response_model=schemas.BenchmarkAdminOut)
def reject_benchmark(benchmark_id: uuid.UUID, body: schemas.ReasonIn, db: DbSession, actor: AnyEditorOrPublisher):
    service.reject_benchmark(db, actor, benchmark_id, reason=body.reason)
    db.commit()
    return _one(db, benchmark_id)


@router.post("/benchmarks/{benchmark_id}/withdraw", response_model=schemas.BenchmarkAdminOut)
def withdraw_benchmark(benchmark_id: uuid.UUID, body: schemas.ReasonIn, db: DbSession, actor: Publisher):
    service.withdraw_benchmark(db, actor, benchmark_id, reason=body.reason)
    db.commit()
    return _one(db, benchmark_id)


@router.get("/audit", response_model=list[schemas.AuditEventOut])
def list_audit_events(
    db: DbSession,
    _: PricingAdmin,
    entity_type: Annotated[str | None, Query(alias="entityType")] = None,
    entity_id: Annotated[uuid.UUID | None, Query(alias="entityId")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    events = repository.audit_events(db, entity_type=entity_type, entity_id=entity_id, limit=limit)
    emails = repository.user_emails(db, [e.actor_id for e in events])
    return [
        schemas.AuditEventOut(
            id=e.id, entity_type=e.entity_type, entity_id=e.entity_id, action=e.action,
            actor=emails.get(e.actor_id), occurred_at=e.occurred_at, from_status=e.from_status,
            to_status=e.to_status, reason=e.reason, changes=e.changes,
        )
        for e in events
    ]
