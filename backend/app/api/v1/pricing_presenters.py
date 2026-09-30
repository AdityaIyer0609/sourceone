"""Maps pricing models and read-model results onto API contracts."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.catalogue.market_average import STALE_AFTER_DAYS, AveragePoint, MarketView, gap
from app.core.clock import business_today
from app.core.config import get_settings
from app.models.catalogue import Grade, Market, Producer
from app.models.pricing import BenchmarkRate, RateSeries, RateSource, SourceRate
from app.pricing import read_model, repository
from app.pricing.constants import (
    HISTORY_RANGES_DAYS,
    PRICE_BASIS_LABELS,
    TAX_BASIS_LABELS,
    UNIT_LABELS,
    label_for,
)
from app.pricing.read_model import PERCENT_QUANTUM, compute_stats
from app.schemas import pricing as schemas


def quote_position(
    offered: Decimal | None, snapshot: Decimal | None, average: Decimal | None, currency: str | None,
) -> schemas.QuotePositionOut:
    versus_snapshot = gap(offered, snapshot)
    versus_average = gap(offered, average)
    return schemas.QuotePositionOut(
        offered_price=money(offered, currency),
        snapshot=money(snapshot, currency),
        current_average=money(average, currency),
        versus_snapshot=money(versus_snapshot, currency),
        versus_average=money(versus_average, currency),
    )


def money(amount: Decimal | None, currency: str | None) -> schemas.Money | None:
    if amount is None or currency is None:
        return None
    return schemas.Money(amount=f"{amount:.4f}", currency=currency)


def _codes(series: RateSeries) -> dict:
    return {
        "price_basis": schemas.CodeLabel(code=series.price_basis, label=label_for(PRICE_BASIS_LABELS, series.price_basis)),
        "tax_basis": schemas.CodeLabel(code=series.tax_basis, label=label_for(TAX_BASIS_LABELS, series.tax_basis)),
        "unit": schemas.CodeLabel(code=series.unit, label=label_for(UNIT_LABELS, series.unit)),
    }


def _point(point: read_model.Point) -> schemas.PointOut:
    return schemas.PointOut(at=point.at, value=f"{point.value:.4f}", benchmark_id=point.benchmark_id)


def _stats(stats: read_model.Stats) -> schemas.StatsOut:
    fmt = lambda v: None if v is None else f"{v:.4f}"  # noqa: E731
    return schemas.StatsOut(
        state=stats.state,
        point_count=stats.point_count,
        high=fmt(stats.high),
        low=fmt(stats.low),
        average=fmt(stats.average),
        volatility=schemas.VolatilityOut(state=stats.volatility_state, level=stats.volatility_level),
    )


def benchmark_summary(series: RateSeries, timeline: list[BenchmarkRate], now: datetime) -> schemas.BenchmarkSummaryOut:
    settings = get_settings()
    current = read_model.resolve_current(timeline, now)
    move = read_model.movement(timeline, current)
    sparkline = read_model.build_history(
        timeline, "7D", now,
        min_points=settings.pricing_history_min_points,
        volatility_min_points=settings.pricing_volatility_min_points,
    )
    current_out = None
    if current.benchmark is not None and current.freshness is not None:
        b = current.benchmark
        current_out = schemas.CurrentOut(
            benchmark_id=b.id,
            value=money(b.value, b.currency),
            effective_from=b.effective_from,
            published_at=b.published_at,
            freshness=schemas.FreshnessOut(
                state=current.freshness.state,
                as_of_date=current.freshness.as_of_date,
                stale_after=current.freshness.stale_after,
            ),
        )
    movement_out = schemas.MovementOut(state=move.state)
    if move.state == "ok" and move.previous is not None:
        movement_out = schemas.MovementOut(
            state="ok",
            previous_value=money(move.previous.value, move.previous.currency),
            previous_as_of_date=move.previous.source_as_of_date,
            absolute=money(move.absolute, series.currency),
            percent=f"{move.percent:.2f}",
        )
    points = ([_point(sparkline.carry_in)] if sparkline.carry_in else []) + [_point(p) for p in sparkline.points]
    return schemas.BenchmarkSummaryOut(
        series_code=series.code,
        name=series.display_name,
        category=series.grade.category,
        grade=schemas.CodeLabel(code=series.grade.code, label=series.grade.name),
        market=schemas.CodeLabel(code=series.market.code, label=series.market.name),
        currency=series.currency,
        availability=current.availability,
        unavailable_reason=current.unavailable_reason,
        current=current_out,
        movement=movement_out,
        sparkline=schemas.SparklineOut(range="7D", state=sparkline.state, points=points),
        **_codes(series),
    )


def _point_id(summary: schemas.BenchmarkSummaryOut, market: MarketView) -> uuid.UUID:
    if market.points:
        return market.points[-1].point_id
    if summary.current is not None:
        return summary.current.benchmark_id
    return uuid.uuid5(uuid.NAMESPACE_URL, f"asking-average:{summary.series_code}:{summary.currency}")


def apply_market_average(summary: schemas.BenchmarkSummaryOut, market: MarketView, now: datetime) -> schemas.BenchmarkSummaryOut:
    """Replace a published series value with the average of supplier asking prices."""
    if market.kind != "average" or market.average is None or market.as_of is None:
        summary.availability = "rate_on_request"
        summary.unavailable_reason = "no_benchmark"
        summary.current = None
        summary.movement = schemas.MovementOut(state="insufficient_data")
        summary.sparkline = schemas.SparklineOut(range="7D", state="insufficient_data", points=[])
        return summary
    point_id = _point_id(summary, market)
    summary.availability = "available"
    summary.unavailable_reason = None
    summary.current = schemas.CurrentOut(
        benchmark_id=point_id,
        value=money(market.average, summary.currency),
        effective_from=market.as_of,
        published_at=market.as_of,
        freshness=schemas.FreshnessOut(
            state="fresh",
            as_of_date=business_today(market.as_of),
            stale_after=now + timedelta(days=STALE_AFTER_DAYS),
        ),
    )
    if market.previous is None:
        summary.movement = schemas.MovementOut(state="insufficient_data")
    else:
        absolute = (market.average - market.previous).quantize(Decimal("0.0001"))
        percent = (absolute / market.previous * 100).quantize(PERCENT_QUANTUM)
        previous_at = market.points[-2].at if len(market.points) >= 2 else market.as_of
        summary.movement = schemas.MovementOut(
            state="ok",
            previous_value=money(market.previous, summary.currency),
            previous_as_of_date=business_today(previous_at),
            absolute=money(absolute, summary.currency),
            percent=f"{percent:.2f}",
        )
    start = now - timedelta(days=7)
    spark = [point for point in market.points if point.at >= start]
    if not spark:
        spark = [AveragePoint(market.as_of, market.average, point_id)]
    summary.sparkline = schemas.SparklineOut(
        range="7D",
        state="ok",
        points=[schemas.PointOut(at=point.at, value=f"{point.value:.4f}", benchmark_id=point.point_id) for point in spark],
    )
    if market.spread_min is not None and market.spread_max is not None:
        summary.spread = schemas.SpreadOut(
            state="ok",
            minimum=money(market.spread_min, summary.currency),
            maximum=money(market.spread_max, summary.currency),
            ask_count=market.supplier_count,
        )
    else:
        summary.spread = schemas.SpreadOut(state="unavailable", ask_count=market.supplier_count)
    return summary


def market_history(series: RateSeries, market: MarketView, range_code: str, now: datetime) -> schemas.HistoryOut:
    start = now - timedelta(days=HISTORY_RANGES_DAYS[range_code])
    stored = list(market.points)
    if market.kind == "average" and market.average is not None and (not stored or stored[-1].value != market.average):
        stored.append(AveragePoint(market.as_of or now, market.average, stored[-1].point_id if stored else series.id))
    carry = [point for point in stored if point.at < start]
    inside = [point for point in stored if point.at >= start]
    carry_in = carry[-1] if carry else None
    values = ([carry_in.value] if carry_in else []) + [point.value for point in inside]
    stats = compute_stats(values, min_points=1, volatility_min_points=get_settings().pricing_volatility_min_points)
    return schemas.HistoryOut(
        series_code=series.code,
        range=range_code,
        currency=series.currency,
        unit=series.unit,
        state=stats.state if values else "insufficient_data",
        carry_in=schemas.PointOut(at=carry_in.at, value=f"{carry_in.value:.4f}", benchmark_id=carry_in.point_id) if carry_in else None,
        points=[schemas.PointOut(at=point.at, value=f"{point.value:.4f}", benchmark_id=point.point_id) for point in inside],
        gaps=[],
        stats=_stats(stats),
    )


def history(series: RateSeries, result: read_model.History) -> schemas.HistoryOut:
    return schemas.HistoryOut(
        series_code=series.code,
        range=result.range_code,
        currency=series.currency,
        unit=series.unit,
        state=result.state,
        carry_in=_point(result.carry_in) if result.carry_in else None,
        points=[_point(p) for p in result.points],
        gaps=[schemas.GapOut(start=g.start, end=g.end, reason=g.reason) for g in result.gaps],
        stats=_stats(result.stats),
    )


def _ref(obj: Producer | Grade | Market | None) -> schemas.RefOut | None:
    if obj is None:
        return None
    return schemas.RefOut(id=obj.id, code=obj.code, name=obj.name)


def source_rate(session: Session, row: SourceRate) -> schemas.SourceRateOut:
    return schemas.SourceRateOut(
        id=row.id,
        source_code=row.source.code,
        import_batch_id=row.import_batch_id,
        source_row_ref=row.source_row_ref,
        source_as_of_date=row.source_as_of_date,
        producer=_ref(session.get(Producer, row.producer_id) if row.producer_id else None),
        raw_producer=row.raw_producer,
        raw_grade=row.raw_grade,
        raw_location=row.raw_location,
        origin_location=row.origin_location,
        raw_sector=row.raw_sector,
        sector=row.sector,
        application=row.application,
        grade=_ref(session.get(Grade, row.grade_id) if row.grade_id else None),
        market=_ref(session.get(Market, row.market_id) if row.market_id else None),
        series_code=row.series.code if row.series else None,
        value=money(row.value, row.currency),
        unit=row.unit,
        price_basis=row.price_basis,
        tax_basis=row.tax_basis,
        resolution_status=row.resolution_status,
        resolution_reason=row.resolution_reason,
        is_benchmark_eligible=row.is_benchmark_eligible,
        eligibility_reason=row.eligibility_reason,
        is_unchanged=row.is_unchanged,
        normalization_profile_version=row.normalization_profile_version,
        created_at=row.created_at,
    )


def series_admin(series: RateSeries, timeline: list[BenchmarkRate], now: datetime) -> schemas.RateSeriesOut:
    current = read_model.resolve_current(timeline, now)
    return schemas.RateSeriesOut(
        id=series.id,
        code=series.code,
        display_name=series.display_name,
        grade=_ref(series.grade),
        market=_ref(series.market),
        currency=series.currency,
        is_active=series.is_active,
        availability=current.availability,
        freshness_state=current.freshness.state if current.freshness else None,
        current_benchmark_id=current.benchmark.id if current.benchmark else None,
        **_codes(series),
    )


def benchmark_admin(session: Session, benchmarks: list[BenchmarkRate]) -> list[schemas.BenchmarkAdminOut]:
    emails = repository.user_emails(
        session,
        [
            uid
            for b in benchmarks
            for uid in (
                b.created_by_id, b.last_edited_by_id, b.submitted_by_id,
                b.published_by_id, b.rejected_by_id, b.withdrawn_by_id,
            )
        ],
    )
    out = []
    for b in benchmarks:
        source = session.get(RateSource, b.primary_source_id)
        inputs = [
            schemas.BenchmarkInputOut(
                source_rate_id=i.source_rate_id,
                role=i.role,
                source_row_ref=i.source_rate.source_row_ref,
                raw_producer=i.source_rate.raw_producer,
                source_as_of_date=i.source_rate.source_as_of_date,
            )
            for i in b.inputs
        ]
        out.append(
            schemas.BenchmarkAdminOut(
                id=b.id,
                series_id=b.series_id,
                series_code=b.series.code,
                status=b.status,
                value=money(b.value, b.currency),
                unit=b.unit,
                price_basis=b.price_basis,
                tax_basis=b.tax_basis,
                method=b.method,
                origin=b.origin,
                is_edited=b.is_edited,
                four_eyes_required=b.four_eyes_required,
                primary_source_code=source.code,
                inputs=inputs,
                source_as_of_date=b.source_as_of_date,
                effective_from=b.effective_from,
                effective_until=b.effective_until,
                staleness_days=b.staleness_days,
                stale_after=b.stale_after,
                reason=b.reason,
                evidence_ref=b.evidence_ref,
                created_by=emails.get(b.created_by_id),
                created_at=b.created_at,
                last_edited_by=emails.get(b.last_edited_by_id),
                last_edited_at=b.last_edited_at,
                submitted_by=emails.get(b.submitted_by_id),
                submitted_at=b.submitted_at,
                published_by=emails.get(b.published_by_id),
                published_at=b.published_at,
                rejected_by=emails.get(b.rejected_by_id),
                rejected_at=b.rejected_at,
                rejected_reason=b.rejected_reason,
                withdrawn_by=emails.get(b.withdrawn_by_id),
                withdrawn_at=b.withdrawn_at,
                withdrawn_reason=b.withdrawn_reason,
                row_version=b.row_version,
            )
        )
    return out
