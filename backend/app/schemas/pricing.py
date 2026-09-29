import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Money(ApiModel):
    amount: str
    currency: str


class CodeLabel(ApiModel):
    code: str
    label: str


class FreshnessOut(ApiModel):
    state: Literal["fresh", "stale"]
    as_of_date: date
    stale_after: datetime


class CurrentOut(ApiModel):
    benchmark_id: uuid.UUID
    value: Money
    effective_from: datetime
    published_at: datetime
    freshness: FreshnessOut


class MovementOut(ApiModel):
    state: Literal["ok", "insufficient_data"]
    previous_value: Money | None = None
    previous_as_of_date: date | None = None
    absolute: Money | None = None
    percent: str | None = None


class PointOut(ApiModel):
    at: datetime
    value: str
    benchmark_id: uuid.UUID


class GapOut(ApiModel):
    start: datetime
    end: datetime
    reason: str


class VolatilityOut(ApiModel):
    state: Literal["ok", "insufficient_data"]
    level: Literal["low", "medium", "high"] | None = None


class StatsOut(ApiModel):
    state: Literal["ok", "insufficient_data"]
    point_count: int
    high: str | None = None
    low: str | None = None
    average: str | None = None
    volatility: VolatilityOut


class SparklineOut(ApiModel):
    range: str
    state: Literal["ok", "insufficient_data"]
    points: list[PointOut]


class BenchmarkSummaryOut(ApiModel):
    """Buyer/supplier contract. Deliberately carries no source or producer information."""

    series_code: str
    name: str
    category: str
    grade: CodeLabel
    market: CodeLabel
    price_basis: CodeLabel
    tax_basis: CodeLabel
    unit: CodeLabel
    currency: str
    price_kind: Literal["sourceone_benchmark"] = "sourceone_benchmark"
    price_label: Literal["SourceOne benchmark"] = "SourceOne benchmark"
    availability: Literal["available", "rate_on_request"]
    unavailable_reason: str | None = None
    current: CurrentOut | None = None
    movement: MovementOut
    sparkline: SparklineOut


class SpecificationOut(ApiModel):
    key: str
    label: str
    value: str | None


class ProductOut(ApiModel):
    """Buyer catalogue product. Prices come only from the mapped SourceOne benchmark series."""

    product_code: str
    name: str
    category: str
    subcategory: str | None
    description: str | None
    uom: CodeLabel
    price_kind: Literal["sourceone_benchmark"] = "sourceone_benchmark"
    price_label: Literal["SourceOne benchmark"] = "SourceOne benchmark"
    availability: Literal["available", "rate_on_request"]
    listing_count: int
    default_series_code: str | None
    pricing: list[BenchmarkSummaryOut]
    specifications: list[SpecificationOut]


class HistoryOut(ApiModel):
    series_code: str
    range: str
    currency: str
    unit: str
    state: Literal["ok", "insufficient_data"]
    carry_in: PointOut | None = None
    points: list[PointOut]
    gaps: list[GapOut]
    stats: StatsOut


class EstimateOut(ApiModel):
    price_kind: Literal["estimated_material_value"] = "estimated_material_value"
    label: str
    informational: bool = True
    series_code: str
    availability: Literal["available", "rate_on_request"]
    quantity: str
    unit: str
    unit_value: Money | None = None
    amount: Money | None = None
    benchmark_id: uuid.UUID | None = None
    freshness_state: Literal["fresh", "stale"] | None = None


# --- Admin contracts -----------------------------------------------------------------------


class BenchmarkFieldIn(ApiModel):
    benchmark_price_field: Literal["GrandTotal", "Total", "Basic", "UnitPrice"]


class RateSourceOut(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    source_type: str
    is_active: bool
    priority: int
    staleness_days: int
    publishing_policy: str
    profile_version: int
    benchmark_price_field: str | None = None


class RefOut(ApiModel):
    id: uuid.UUID
    code: str
    name: str


class SourceRateOut(ApiModel):
    id: uuid.UUID
    source_code: str
    import_batch_id: uuid.UUID | None
    source_row_ref: str
    source_as_of_date: date
    producer: RefOut | None
    raw_producer: str | None
    raw_grade: str | None
    raw_location: str | None
    origin_location: str | None
    raw_sector: str | None
    sector: str | None
    application: str | None
    grade: RefOut | None
    market: RefOut | None
    series_code: str | None
    value: Money | None
    unit: str | None
    price_basis: str | None
    tax_basis: str | None
    resolution_status: str
    resolution_reason: str | None
    is_benchmark_eligible: bool
    eligibility_reason: str | None
    is_unchanged: bool
    normalization_profile_version: int
    created_at: datetime


class RateSeriesOut(ApiModel):
    id: uuid.UUID
    code: str
    display_name: str
    grade: RefOut
    market: RefOut
    price_basis: CodeLabel
    tax_basis: CodeLabel
    currency: str
    unit: CodeLabel
    is_active: bool
    availability: Literal["available", "rate_on_request"]
    freshness_state: Literal["fresh", "stale"] | None = None
    current_benchmark_id: uuid.UUID | None = None


class BenchmarkInputOut(ApiModel):
    source_rate_id: uuid.UUID
    role: str
    source_row_ref: str
    raw_producer: str | None
    source_as_of_date: date


class BenchmarkAdminOut(ApiModel):
    id: uuid.UUID
    series_id: uuid.UUID
    series_code: str
    status: str
    value: Money
    unit: str
    price_basis: str
    tax_basis: str
    method: str
    origin: str
    is_edited: bool
    four_eyes_required: bool
    primary_source_code: str
    inputs: list[BenchmarkInputOut]
    source_as_of_date: date
    effective_from: datetime
    effective_until: datetime | None
    staleness_days: int | None
    stale_after: datetime | None
    reason: str | None
    evidence_ref: str | None
    created_by: str | None
    created_at: datetime
    last_edited_by: str | None
    last_edited_at: datetime | None
    submitted_by: str | None
    submitted_at: datetime | None
    published_by: str | None
    published_at: datetime | None
    rejected_by: str | None
    rejected_at: datetime | None
    rejected_reason: str | None
    withdrawn_by: str | None
    withdrawn_at: datetime | None
    withdrawn_reason: str | None
    row_version: int


class SeriesTimelineOut(ApiModel):
    series: RateSeriesOut
    benchmarks: list[BenchmarkAdminOut]


class CreateBenchmarkIn(ApiModel):
    mode: Literal["select_source_rate", "manual"]
    source_rate_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    value: Decimal | None = Field(default=None, gt=0)
    currency: str | None = None
    unit: str | None = None
    source_as_of_date: date | None = None
    reason: str | None = None
    evidence_ref: str | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None


class EditBenchmarkIn(ApiModel):
    row_version: int
    value: Decimal | None = Field(default=None, gt=0)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    source_rate_id: uuid.UUID | None = None
    reason: str | None = None
    evidence_ref: str | None = None


class ReasonIn(ApiModel):
    reason: str = Field(min_length=3, max_length=2000)


class AuditEventOut(ApiModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor: str | None
    occurred_at: datetime
    from_status: str | None
    to_status: str | None
    reason: str | None
    changes: dict | None
