"""Admin-only integration endpoints. The ERP is read-only: these endpoints pull from it, never push."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.identity.service import Actor
from app.integrations.erp import sync
from app.integrations.erp.constants import IntegrationPermission
from app.integrations.erp.factory import get_erp_reader
from app.integrations.erp.reader import ErpReader
from app.models.pricing import ImportBatch
from app.schemas.erp import ErpSyncOut, ErpSyncStats, ImportBatchRef

router = APIRouter(prefix="/admin/integrations", tags=["admin-integrations"])

# Declared before the reader so callers without the permission get 403, not an ERP status.
ErpSyncAdmin = Annotated[Actor, Depends(require_any(IntegrationPermission.ERP_SYNC))]
Reader = Annotated[ErpReader, Depends(get_erp_reader)]


@router.post("/erp/sync", response_model=ErpSyncOut)
def sync_erp(db: DbSession, actor: ErpSyncAdmin, reader: Reader):
    run = sync.run_sync(db, actor, reader)
    db.commit()
    batch = db.get(ImportBatch, run.import_batch_id) if run.import_batch_id else None
    return ErpSyncOut(
        **ErpSyncStats.model_validate(run.stats).model_dump(),
        run_id=run.id,
        adapter=run.adapter,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        snapshot_sys_date=run.snapshot_sys_date,
        snapshot_as_of_date=run.snapshot_as_of_date,
        import_batch=ImportBatchRef(
            id=batch.id, status=batch.status, source_as_of_date=batch.source_as_of_date, row_count=batch.row_count,
            resolved_count=batch.resolved_count, unresolved_count=batch.unresolved_count,
            ineligible_count=batch.ineligible_count,
        ) if batch else None,
    )
