"""Company threshold and the approval queue. An approval is not an order."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.api.v1.pricing_presenters import money
from app.identity.constants import IdentityPermission
from app.identity.service import Actor
from app.models.approval import OrderApproval
from app.orders import approvals
from app.orders.constants import OrderPermission
from app.schemas.approval import ApprovalOut, CompanyOut, CompanyUserOut, DecisionIn, ThresholdIn

router = APIRouter(tags=["approvals"])

Reader = Annotated[Actor, Depends(require_any(OrderPermission.APPROVE, OrderPermission.PLACE))]
Approver = Annotated[Actor, Depends(require_any(OrderPermission.APPROVE))]
CompanyReader = Annotated[Actor, Depends(require_any(
    OrderPermission.PLACE, OrderPermission.APPROVE, IdentityPermission.ORGANISATION, IdentityPermission.MANAGE,
))]
CompanyEditor = Annotated[Actor, Depends(require_any(IdentityPermission.ORGANISATION, IdentityPermission.MANAGE))]


def _present(row: OrderApproval) -> ApprovalOut:
    return ApprovalOut(
        id=row.id,
        status=row.status,
        negotiation_id=row.negotiation_id,
        negotiation_number=row.negotiation.negotiation_number,
        product_name=row.negotiation.product.name,
        amount=money(row.amount, row.currency),
        threshold=money(row.threshold_amount, row.threshold_currency),
        destination_pin=row.destination_pin,
        freight_basis=row.freight_basis,
        submitted_by=row.submitted_by.full_name,
        decided_by=row.decided_by.full_name if row.decided_by is not None else None,
        decision_note=row.decision_note,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


@router.get("/order-approvals", response_model=list[ApprovalOut])
def get_approvals(db: DbSession, actor: Reader):
    return [_present(row) for row in approvals.list_approvals(db, actor)]


@router.post("/order-approvals/{approval_id}/approve", response_model=ApprovalOut)
def post_approve(approval_id: uuid.UUID, db: DbSession, actor: Approver):
    row = approvals.approve(db, actor, approval_id)
    db.commit()
    return _present(row)


@router.post("/order-approvals/{approval_id}/decline", response_model=ApprovalOut)
def post_decline(approval_id: uuid.UUID, db: DbSession, actor: Approver, body: DecisionIn | None = None):
    row = approvals.decline(db, actor, approval_id, note=body.note if body else None)
    db.commit()
    return _present(row)


@router.post("/order-approvals/{approval_id}/reject-deal", response_model=ApprovalOut)
def post_reject_deal(approval_id: uuid.UUID, db: DbSession, actor: Approver, body: DecisionIn | None = None):
    row = approvals.reject_deal(db, actor, approval_id, note=body.note if body else None)
    db.commit()
    return _present(row)


@router.get("/organisation", response_model=CompanyOut)
def get_company(db: DbSession, actor: CompanyReader):
    organisation, users = approvals.company(db, actor)
    return CompanyOut(
        id=organisation.id,
        name=organisation.name,
        threshold=money(organisation.approval_threshold_amount, organisation.approval_threshold_currency),
        users=None if users is None else [
            CompanyUserOut(
                id=user.id, full_name=user.full_name, email=user.email,
                roles=approvals.roles_for(db, user.id), is_active=user.is_active,
            )
            for user in users
        ],
    )


@router.put("/organisation/threshold", response_model=CompanyOut)
def put_threshold(body: ThresholdIn, db: DbSession, actor: CompanyEditor):
    approvals.set_threshold(db, actor, amount=body.amount, currency=body.currency)
    db.commit()
    organisation, users = approvals.company(db, actor)
    return CompanyOut(
        id=organisation.id,
        name=organisation.name,
        threshold=money(organisation.approval_threshold_amount, organisation.approval_threshold_currency),
        users=None if users is None else [
            CompanyUserOut(
                id=user.id, full_name=user.full_name, email=user.email,
                roles=approvals.roles_for(db, user.id), is_active=user.is_active,
            )
            for user in users
        ],
    )
