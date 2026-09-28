"""Buyer-facing view of published benchmarks: current rate, freshness, movement and history."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
import uuid

from app.models.pricing import BenchmarkRate
from app.pricing.constants import (
    HISTORY_RANGES_DAYS,
    VOLATILITY_LOW_BELOW_PCT,
    VOLATILITY_MEDIUM_BELOW_PCT,
    BenchmarkStatus,
)

PRICE_QUANTUM = Decimal("0.0001")
PERCENT_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class Freshness:
    state: str  # "fresh" | "stale"
    as_of_date: date
    stale_after: datetime


@dataclass(frozen=True)
class CurrentBenchmark:
    availability: str  # "available" | "rate_on_request"
    benchmark: BenchmarkRate | None = None
    freshness: Freshness | None = None
    unavailable_reason: str | None = None  # "no_benchmark" | "withdrawn" | "expired"


@dataclass(frozen=True)
class Movement:
    state: str  # "ok" | "insufficient_data"
    previous: BenchmarkRate | None = None
    absolute: Decimal | None = None
    percent: Decimal | None = None


@dataclass(frozen=True)
class Point:
    at: datetime
    value: Decimal
    benchmark_id: uuid.UUID


@dataclass(frozen=True)
class Gap:
    start: datetime
    end: datetime
    reason: str


@dataclass(frozen=True)
class Stats:
    state: str
    point_count: int
    high: Decimal | None = None
    low: Decimal | None = None
    average: Decimal | None = None
    volatility_state: str = "insufficient_data"
    volatility_level: str | None = None


@dataclass(frozen=True)
class History:
    range_code: str
    state: str
    stats: Stats
    carry_in: Point | None = None
    points: list[Point] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)


def _was_effective(benchmark: BenchmarkRate) -> bool:
    if benchmark.status == BenchmarkStatus.PUBLISHED:
        return True
    # A benchmark withdrawn before it took effect never became current and leaves no trace.
    return (
        benchmark.status == BenchmarkStatus.WITHDRAWN
        and benchmark.withdrawn_at is not None
        and benchmark.withdrawn_at >= benchmark.effective_from
    )


def effective_timeline(benchmarks: Sequence[BenchmarkRate], now: datetime) -> list[BenchmarkRate]:
    return sorted(
        (b for b in benchmarks if b.effective_from <= now and _was_effective(b)),
        key=lambda b: b.effective_from,
    )


def resolve_current(benchmarks: Sequence[BenchmarkRate], now: datetime) -> CurrentBenchmark:
    timeline = effective_timeline(benchmarks, now)
    if not timeline:
        return CurrentBenchmark("rate_on_request", unavailable_reason="no_benchmark")
    latest = timeline[-1]
    # Never fall back to an older benchmark after a withdrawal or expiry.
    if latest.status == BenchmarkStatus.WITHDRAWN:
        return CurrentBenchmark("rate_on_request", unavailable_reason="withdrawn")
    if latest.effective_until is not None and latest.effective_until <= now:
        return CurrentBenchmark("rate_on_request", unavailable_reason="expired")
    state = "stale" if now >= latest.stale_after else "fresh"
    return CurrentBenchmark(
        "available",
        benchmark=latest,
        freshness=Freshness(state=state, as_of_date=latest.source_as_of_date, stale_after=latest.stale_after),
    )


def movement(benchmarks: Sequence[BenchmarkRate], current: CurrentBenchmark) -> Movement:
    if current.benchmark is None:
        return Movement("insufficient_data")
    earlier = [
        b
        for b in benchmarks
        if b.status == BenchmarkStatus.PUBLISHED and b.effective_from < current.benchmark.effective_from
    ]
    if not earlier:
        return Movement("insufficient_data")
    previous = max(earlier, key=lambda b: b.effective_from)
    absolute = (current.benchmark.value - previous.value).quantize(PRICE_QUANTUM)
    percent = (absolute / previous.value * 100).quantize(PERCENT_QUANTUM)
    return Movement("ok", previous=previous, absolute=absolute, percent=percent)


def compute_stats(values: Sequence[Decimal], *, min_points: int, volatility_min_points: int) -> Stats:
    count = len(values)
    if count < min_points or count == 0:
        return Stats(state="insufficient_data", point_count=count)
    high, low = max(values), min(values)
    average = (sum(values) / count).quantize(PRICE_QUANTUM)
    volatility_state, level = "insufficient_data", None
    if count >= volatility_min_points:
        changes = [float((b - a) / a * 100) for a, b in zip(values, values[1:])]
        deviation = statistics.pstdev(changes)
        volatility_state = "ok"
        if deviation < VOLATILITY_LOW_BELOW_PCT:
            level = "low"
        elif deviation < VOLATILITY_MEDIUM_BELOW_PCT:
            level = "medium"
        else:
            level = "high"
    return Stats(
        state="ok",
        point_count=count,
        high=high,
        low=low,
        average=average,
        volatility_state=volatility_state,
        volatility_level=level,
    )


def build_history(
    benchmarks: Sequence[BenchmarkRate],
    range_code: str,
    now: datetime,
    *,
    min_points: int,
    volatility_min_points: int,
) -> History:
    start = now - timedelta(days=HISTORY_RANGES_DAYS[range_code])
    timeline = effective_timeline(benchmarks, now)

    points = [
        Point(b.effective_from, b.value, b.id)
        for b in timeline
        if b.status == BenchmarkStatus.PUBLISHED and b.effective_from >= start
    ]

    carry_in = None
    before = [b for b in timeline if b.effective_from < start]
    if before:
        last = before[-1]
        if last.status == BenchmarkStatus.PUBLISHED and (
            last.effective_until is None or last.effective_until > start
        ):
            carry_in = Point(start, last.value, last.id)

    gaps: list[Gap] = []
    for index, item in enumerate(timeline):
        segment_end = timeline[index + 1].effective_from if index + 1 < len(timeline) else now
        if item.status == BenchmarkStatus.WITHDRAWN:
            gap = (item.effective_from, segment_end, "withdrawn")
        elif item.effective_until is not None and item.effective_until < segment_end:
            gap = (item.effective_until, segment_end, "expired")
        else:
            continue
        gap_start, gap_end = max(gap[0], start), min(gap[1], now)
        if gap_start < gap_end:
            gaps.append(Gap(gap_start, gap_end, gap[2]))

    values = ([carry_in.value] if carry_in else []) + [p.value for p in points]
    stats = compute_stats(values, min_points=min_points, volatility_min_points=volatility_min_points)
    return History(
        range_code=range_code,
        state=stats.state,
        stats=stats,
        carry_in=carry_in,
        points=points,
        gaps=gaps,
    )
