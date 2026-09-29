import uuid
from datetime import date, datetime

from app.schemas.pricing import ApiModel


class RejectedPriceRow(ApiModel):
    sr_no: int | None
    sys_date: datetime | None
    reason: str


class ErpGradeRef(ApiModel):
    found: bool
    mapping_status: str | None = None
    erp_item_code: str | None = None


class UnresolvedGrade(ApiModel):
    company: str | None
    quality: str | None = None
    grade: str | None
    reason: str
    row_count: int
    sr_nos: list[int]
    erp_grade_master: ErpGradeRef


class SyncWarning(ApiModel):
    code: str
    count: int
    message: str


class PriceSyncStats(ApiModel):
    rows_read: int = 0
    rejected: int = 0
    already_imported: int = 0
    skipped: int = 0
    imported: int = 0
    resolved: int = 0
    unresolved: int = 0
    ineligible: int = 0
    flagged_by_reason: dict[str, int] = {}
    rejected_rows: list[RejectedPriceRow] = []
    suggestions_submitted_for_review: int = 0
    benchmarks_published: int = 0


class GradeSyncStats(ApiModel):
    rows_read: int = 0
    rejected: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    mapped: int = 0
    unmapped_producer: int = 0
    unmapped_grade: int = 0


class CustomerSyncStats(ApiModel):
    rows_read: int = 0
    rejected: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    missing_gstin: int = 0
    invalid_gstin: int = 0
    missing_pin: int = 0
    invalid_pin: int = 0


class ImportBatchRef(ApiModel):
    id: uuid.UUID
    status: str
    source_as_of_date: date
    row_count: int
    resolved_count: int
    unresolved_count: int
    ineligible_count: int


class ErpSyncStats(ApiModel):
    rows_read: int = 0
    imported: int = 0
    skipped: int = 0
    rejected: int = 0
    warnings: list[SyncWarning] = []
    prices: PriceSyncStats
    grades: GradeSyncStats
    customers: CustomerSyncStats
    unresolved_grades: list[UnresolvedGrade]


class ErpSyncOut(ErpSyncStats):
    run_id: uuid.UUID
    adapter: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    snapshot_sys_date: datetime | None
    snapshot_as_of_date: date | None
    import_batch: ImportBatchRef | None
