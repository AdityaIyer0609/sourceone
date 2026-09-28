import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.catalogue import Grade, Market
from app.pricing.constants import (
    BenchmarkMethod,
    BenchmarkOrigin,
    BenchmarkStatus,
    ImportBatchStatus,
    InputRole,
    PublishingPolicy,
    ResolutionStatus,
    Sector,
    SeriesVisibility,
    SourceType,
    SUPPORTED_CURRENCIES,
    SUPPORTED_UNITS,
)

PRICE = Numeric(18, 4)


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(str(v)) for v in values)})"


class RateSource(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "rate_sources"
    __table_args__ = (
        CheckConstraint(_in("source_type", SourceType), name="source_type"),
        CheckConstraint(_in("publishing_policy", PublishingPolicy), name="publishing_policy"),
        CheckConstraint("staleness_days > 0", name="staleness_days_positive"),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    priority: Mapped[int] = mapped_column(Integer)
    staleness_days: Mapped[int] = mapped_column(Integer)
    publishing_policy: Mapped[str] = mapped_column(String(32))
    default_currency: Mapped[str | None] = mapped_column(String(3))
    default_unit: Mapped[str | None] = mapped_column(String(16))
    normalization_profile: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    profile_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    owner_organisation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.id"))
    description: Mapped[str | None] = mapped_column(Text)


class RateSeries(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "rate_series"
    __table_args__ = (
        UniqueConstraint(
            "grade_id", "market_id", "price_basis", "tax_basis", "currency", "unit",
            name="uq_rate_series_definition",
        ),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
        CheckConstraint(_in("unit", SUPPORTED_UNITS), name="unit"),
        CheckConstraint(_in("visibility", SeriesVisibility), name="visibility"),
    )

    code: Mapped[str] = mapped_column(String(160), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    grade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grades.id"))
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("markets.id"), index=True)
    price_basis: Mapped[str] = mapped_column(String(32))
    tax_basis: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    unit: Mapped[str] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    grade: Mapped[Grade] = relationship()
    market: Mapped[Market] = relationship()


class ImportBatch(UUIDPrimaryKey, Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "source_as_of_date", "checksum", name="uq_import_batches_source_date_checksum"
        ),
        CheckConstraint(_in("status", ImportBatchStatus), name="status"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rate_sources.id"), index=True)
    source_as_of_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    triggered_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    resolved_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unresolved_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ineligible_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class SourceRate(UUIDPrimaryKey, Base):
    """A price exactly as received from a source, plus its normalisation and catalogue resolution."""

    __tablename__ = "source_rates"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "source_row_key", name="uq_source_rates_batch_row_key"),
        CheckConstraint(_in("resolution_status", ResolutionStatus), name="resolution_status"),
        CheckConstraint(f"sector IS NULL OR {_in('sector', Sector)}", name="sector"),
        CheckConstraint("value IS NULL OR value > 0", name="value_positive"),
        CheckConstraint(
            "resolution_status <> 'resolved' OR (value IS NOT NULL AND currency IS NOT NULL "
            "AND unit IS NOT NULL AND grade_id IS NOT NULL AND market_id IS NOT NULL)",
            name="resolved_is_complete",
        ),
        CheckConstraint(
            "NOT is_benchmark_eligible OR (resolution_status = 'resolved' AND series_id IS NOT NULL)",
            name="eligible_requires_series",
        ),
        Index("ix_source_rates_identity", "source_id", "source_identity_key", "source_as_of_date"),
        Index("ix_source_rates_series_as_of", "series_id", "source_as_of_date"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rate_sources.id"))
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_batches.id"))
    source_row_ref: Mapped[str] = mapped_column(String(128))
    source_row_key: Mapped[str] = mapped_column(String(128))
    source_identity_key: Mapped[str] = mapped_column(String(128))
    source_as_of_date: Mapped[date] = mapped_column(Date)

    raw_producer: Mapped[str | None] = mapped_column(String(255))
    raw_grade: Mapped[str | None] = mapped_column(String(255))
    raw_location: Mapped[str | None] = mapped_column(String(255))
    raw_sector: Mapped[str | None] = mapped_column(String(64))
    origin_location: Mapped[str | None] = mapped_column(String(255))
    application: Mapped[str | None] = mapped_column(String(64))
    sector: Mapped[str | None] = mapped_column(String(16))

    producer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("producers.id"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id"))
    market_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("markets.id"))
    series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rate_series.id"))
    producer_grade_alias_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("producer_grade_aliases.id")
    )
    grade_equivalence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("grade_equivalence.id")
    )
    market_alias_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("market_aliases.id"))

    value: Mapped[Decimal | None] = mapped_column(PRICE)
    currency: Mapped[str | None] = mapped_column(String(3))
    unit: Mapped[str | None] = mapped_column(String(16))
    price_basis: Mapped[str | None] = mapped_column(String(32))
    tax_basis: Mapped[str | None] = mapped_column(String(32))

    resolution_status: Mapped[str] = mapped_column(String(16))
    resolution_reason: Mapped[str | None] = mapped_column(String(64))
    is_benchmark_eligible: Mapped[bool] = mapped_column(default=False, server_default=false())
    eligibility_reason: Mapped[str | None] = mapped_column(String(64))
    is_unchanged: Mapped[bool] = mapped_column(default=False, server_default=false())

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    normalization_profile_version: Mapped[int] = mapped_column(Integer)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    source: Mapped[RateSource] = relationship()
    series: Mapped[RateSeries | None] = relationship()


class BenchmarkRate(UUIDPrimaryKey, Base):
    """A SourceOne-published reference price. Once published, only withdrawal is allowed."""

    __tablename__ = "benchmark_rates"
    __table_args__ = (
        CheckConstraint(_in("status", BenchmarkStatus), name="status"),
        CheckConstraint(_in("method", BenchmarkMethod), name="method"),
        CheckConstraint(_in("origin", BenchmarkOrigin), name="origin"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
        CheckConstraint(_in("unit", SUPPORTED_UNITS), name="unit"),
        CheckConstraint("value > 0", name="value_positive"),
        CheckConstraint(
            "effective_until IS NULL OR effective_until > effective_from", name="effective_window"
        ),
        CheckConstraint(
            "method <> 'manual' OR (reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="manual_requires_reason",
        ),
        CheckConstraint(
            "status NOT IN ('published', 'withdrawn') OR (published_at IS NOT NULL "
            "AND published_by_id IS NOT NULL AND stale_after IS NOT NULL AND staleness_days IS NOT NULL)",
            name="published_is_complete",
        ),
        CheckConstraint(
            "status <> 'withdrawn' OR (withdrawn_at IS NOT NULL AND withdrawn_by_id IS NOT NULL "
            "AND withdrawn_reason IS NOT NULL)",
            name="withdrawn_is_complete",
        ),
        CheckConstraint(
            "status <> 'rejected' OR (rejected_at IS NOT NULL AND rejected_by_id IS NOT NULL "
            "AND rejected_reason IS NOT NULL)",
            name="rejected_is_complete",
        ),
        Index(
            "uq_benchmark_rates_series_effective_from",
            "series_id",
            "effective_from",
            unique=True,
            postgresql_where=text("status IN ('published', 'withdrawn')"),
        ),
        Index("ix_benchmark_rates_series_status", "series_id", "status"),
    )

    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rate_series.id"))
    primary_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rate_sources.id"))
    value: Mapped[Decimal] = mapped_column(PRICE)
    currency: Mapped[str] = mapped_column(String(3))
    unit: Mapped[str] = mapped_column(String(16))
    price_basis: Mapped[str] = mapped_column(String(32))
    tax_basis: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(32))
    is_edited: Mapped[bool] = mapped_column(default=False, server_default=false())
    four_eyes_required: Mapped[bool] = mapped_column()
    status: Mapped[str] = mapped_column(String(16))

    source_as_of_date: Mapped[date] = mapped_column(Date)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staleness_days: Mapped[int | None] = mapped_column(Integer)
    stale_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reason: Mapped[str | None] = mapped_column(Text)
    evidence_ref: Mapped[str | None] = mapped_column(String(255))

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_edited_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)

    row_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    series: Mapped[RateSeries] = relationship()
    primary_source: Mapped[RateSource] = relationship()
    inputs: Mapped[list["BenchmarkRateInput"]] = relationship(
        back_populates="benchmark_rate", cascade="all, delete-orphan"
    )

    __mapper_args__ = {"version_id_col": row_version}


class BenchmarkRateInput(UUIDPrimaryKey, Base):
    __tablename__ = "benchmark_rate_inputs"
    __table_args__ = (
        UniqueConstraint("benchmark_rate_id", "source_rate_id", name="uq_benchmark_rate_inputs_pair"),
        CheckConstraint(_in("role", InputRole), name="role"),
        Index(
            "uq_benchmark_rate_inputs_one_primary",
            "benchmark_rate_id",
            unique=True,
            postgresql_where=text("role = 'primary'"),
        ),
    )

    benchmark_rate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("benchmark_rates.id", ondelete="CASCADE")
    )
    source_rate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_rates.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    benchmark_rate: Mapped[BenchmarkRate] = relationship(back_populates="inputs")
    source_rate: Mapped[SourceRate] = relationship()


class PricingAuditEvent(UUIDPrimaryKey, Base):
    __tablename__ = "pricing_audit_events"
    __table_args__ = (
        Index("ix_pricing_audit_events_entity", "entity_type", "entity_id", "occurred_at"),
    )

    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
