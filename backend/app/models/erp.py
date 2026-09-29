"""SourceOne-owned copies of read-only ERP reference data, plus the audit trail of ERP syncs.

Nothing here is ever written back to the ERP.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.db.base import Base, UUIDPrimaryKey
from app.integrations.erp.constants import GSTIN_PATTERN, PIN_PATTERN, GradeMappingStatus, SyncRunStatus


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(str(v)) for v in values)})"


class ErpSyncRun(UUIDPrimaryKey, Base):
    __tablename__ = "erp_sync_runs"
    __table_args__ = (CheckConstraint(_in("status", SyncRunStatus), name="status"),)

    triggered_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    adapter: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ERP SysDate is a local (IST) smalldatetime without a zone; kept exactly as read.
    snapshot_sys_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    snapshot_as_of_date: Mapped[date | None] = mapped_column(Date)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_batches.id"))
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ErpPriceRowImport(UUIDPrimaryKey, Base):
    """One row per imported DomesticPrice1 line; SysDate + SrNo can only ever be imported once per source."""

    __tablename__ = "erp_price_row_imports"
    __table_args__ = (
        UniqueConstraint("source_id", "erp_sys_date", "erp_sr_no", name="uq_erp_price_row_imports_identity"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rate_sources.id"))
    erp_sys_date: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    erp_sr_no: Mapped[int] = mapped_column(Integer)
    source_rate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_rates.id"), unique=True)
    sync_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("erp_sync_runs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ErpGrade(UUIDPrimaryKey, Base):
    """DomesticGrade reference line and how it resolves to the SourceOne catalogue (never auto-mapped)."""

    __tablename__ = "erp_grades"
    __table_args__ = (
        UniqueConstraint(
            "company_normalized", "quality_normalized", "grade_normalized", name="uq_erp_grades_identity"
        ),
        CheckConstraint(_in("mapping_status", GradeMappingStatus), name="mapping_status"),
    )

    company: Mapped[str] = mapped_column(String(128))
    company_normalized: Mapped[str] = mapped_column(String(128))
    quality: Mapped[str | None] = mapped_column(String(64))
    quality_normalized: Mapped[str] = mapped_column(String(64), default="", server_default="")
    grade: Mapped[str] = mapped_column(String(128))
    grade_normalized: Mapped[str] = mapped_column(String(128))
    erp_sr_no: Mapped[int | None] = mapped_column(Integer)
    mfi: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    density: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    erp_item_code: Mapped[str | None] = mapped_column(String(64))
    producer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("producers.id"))
    producer_grade_alias_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("producer_grade_aliases.id"))
    mapping_status: Mapped[str] = mapped_column(String(24))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sync_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("erp_sync_runs.id"))


class ErpCustomer(UUIDPrimaryKey, Base):
    """Customer identity only: name, GSTIN and PIN. No bank, PAN, ledger or credit data."""

    __tablename__ = "erp_customers"
    __table_args__ = (
        CheckConstraint(f"gstin IS NULL OR gstin ~ '{GSTIN_PATTERN}'", name="gstin_format"),
        CheckConstraint(f"pin_code IS NULL OR pin_code ~ '{PIN_PATTERN}'", name="pin_format"),
    )

    erp_name: Mapped[str] = mapped_column(String(255), unique=True)
    gstin: Mapped[str | None] = mapped_column(String(15))
    pin_code: Mapped[str | None] = mapped_column(String(6))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sync_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("erp_sync_runs.id"))
