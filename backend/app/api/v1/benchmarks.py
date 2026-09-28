"""Buyer/supplier benchmark endpoints (signed-in users with pricing.view)."""

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, require_any
from app.api.v1 import pricing_presenters as present
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import NotFound
from app.identity.service import Actor
from app.models.catalogue import Grade, Market
from app.models.pricing import RateSeries
from app.pricing import comparison, read_model, repository
from app.pricing.constants import ESTIMATE_LABEL, PricingPermission, SeriesVisibility
from app.schemas import pricing as schemas

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])

Viewer = Annotated[Actor, Depends(require_any(PricingPermission.VIEW))]
RangeCode = Literal["1D", "7D", "1M", "3M", "1Y"]


def _visible_series(db: DbSession, code: str) -> RateSeries:
    series = repository.get_series_by_code(db, code)
    if not series.is_active or series.visibility != SeriesVisibility.SIGNED_IN_PLATFORM:
        raise NotFound(f"Rate series {code!r} not found")
    return series


@router.get("", response_model=list[schemas.BenchmarkSummaryOut])
def list_current_benchmarks(
    db: DbSession,
    _: Viewer,
    category: str | None = None,
    market: str | None = None,
    currency: str | None = None,
):
    stmt = (
        select(RateSeries)
        .join(Grade, Grade.id == RateSeries.grade_id)
        .join(Market, Market.id == RateSeries.market_id)
        .where(RateSeries.is_active.is_(True), RateSeries.visibility == SeriesVisibility.SIGNED_IN_PLATFORM)
        .options(selectinload(RateSeries.grade), selectinload(RateSeries.market))
        .order_by(RateSeries.display_order, RateSeries.code)
    )
    if category:
        stmt = stmt.where(Grade.category == category)
    if market:
        stmt = stmt.where(Market.code == market)
    if currency:
        stmt = stmt.where(RateSeries.currency == currency.upper())
    series_list = db.scalars(stmt).all()
    timelines = repository.timelines(db, [s.id for s in series_list])
    now = utcnow()
    return [present.benchmark_summary(s, timelines.get(s.id, []), now) for s in series_list]


@router.get("/{series_code}", response_model=schemas.BenchmarkSummaryOut)
def get_benchmark(series_code: str, db: DbSession, _: Viewer):
    series = _visible_series(db, series_code)
    timeline = repository.timelines(db, [series.id]).get(series.id, [])
    return present.benchmark_summary(series, timeline, utcnow())


@router.get("/{series_code}/history", response_model=schemas.HistoryOut)
def get_benchmark_history(
    series_code: str,
    db: DbSession,
    _: Viewer,
    range_code: Annotated[RangeCode, Query(alias="range")] = "1M",
):
    settings = get_settings()
    series = _visible_series(db, series_code)
    timeline = repository.timelines(db, [series.id]).get(series.id, [])
    result = read_model.build_history(
        timeline, range_code, utcnow(),
        min_points=settings.pricing_history_min_points,
        volatility_min_points=settings.pricing_volatility_min_points,
    )
    return present.history(series, result)


@router.get("/{series_code}/estimate", response_model=schemas.EstimateOut)
def estimate_material_value(
    series_code: str,
    db: DbSession,
    _: Viewer,
    quantity: Annotated[Decimal, Query(gt=0)],
    unit: str = "KG",
):
    series = _visible_series(db, series_code)
    timeline = repository.timelines(db, [series.id]).get(series.id, [])
    current = read_model.resolve_current(timeline, utcnow())
    estimate = comparison.estimate_material_value(quantity, unit.upper(), current)
    if estimate is None:
        return schemas.EstimateOut(
            label=ESTIMATE_LABEL, series_code=series.code, availability="rate_on_request",
            quantity=str(quantity), unit=series.unit,
        )
    return schemas.EstimateOut(
        label=estimate.label,
        series_code=series.code,
        availability="available",
        quantity=str(estimate.quantity),
        unit=estimate.unit,
        unit_value=present.money(estimate.unit_value, estimate.currency),
        amount=schemas.Money(amount=f"{estimate.amount:.2f}", currency=estimate.currency),
        benchmark_id=estimate.benchmark_id,
        freshness_state=estimate.freshness_state,
    )
