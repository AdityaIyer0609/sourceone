"""Purchase requests. Supplier replies happen on the negotiation this request opens."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.api.v1.negotiations import quantity_text
from app.api.v1.pricing_presenters import money
from app.identity.service import Actor
from app.models.purchase_request import PurchaseRequest
from app.negotiation.constants import NegotiationPermission
from app.purchase_requests import service
from app.purchase_requests.constants import RequestStatus
from app.schemas.purchase_request import PurchaseRequestIn, PurchaseRequestOut, RequestSupplierOut, SuppliersIn

router = APIRouter(prefix="/purchase-requests", tags=["purchase-requests"])

Participant = Annotated[Actor, Depends(require_any(NegotiationPermission.BUY, NegotiationPermission.SUPPLY))]


def _present(actor: Actor, request: PurchaseRequest, db: DbSession) -> PurchaseRequestOut:
    buyer = request.buyer_user_id == actor.user_id and actor.has(NegotiationPermission.BUY)
    visible = request.suppliers if buyer else [
        row for row in request.suppliers if row.supplier_user_id == actor.user_id
    ]
    suppliers = []
    for row in visible:
        estimate = service.freight_for(db, request, row.supplier_user_id)
        currency = estimate["currency"]
        negotiation = row.negotiation
        suppliers.append(RequestSupplierOut(
            supplier_user_id=row.supplier_user_id,
            supplier_name=row.supplier.full_name,
            organisation=row.supplier.organisation.name,
            negotiation_id=negotiation.id if negotiation else None,
            negotiation_number=negotiation.negotiation_number if negotiation else None,
            negotiation_status=negotiation.status if negotiation else None,
            asking_price=money(estimate["asking_price"], currency) if estimate["asking_price"] is not None else None,
            freight_status=estimate["status"],
            freight=money(estimate["freight"], currency) if estimate["freight"] is not None else None,
        ))
    return PurchaseRequestOut(
        id=request.id,
        request_number=request.request_number,
        status=request.status,
        product_code=request.product.product_code,
        product_name=request.product.name,
        quantity=quantity_text(request.quantity),
        uom=request.uom,
        destination_pin=request.destination_pin,
        message=request.message,
        buyer_name=request.buyer.full_name,
        buyer_organisation=request.buyer.organisation.name,
        viewer_role="buyer" if buyer else "supplier",
        suppliers=suppliers,
        can_edit_suppliers=buyer and request.status == RequestStatus.DRAFT,
        can_send=buyer and request.status == RequestStatus.DRAFT and bool(request.suppliers),
        can_cancel=buyer and request.status in service.OPEN_FOR_CANCEL,
        created_at=request.created_at,
    )


@router.get("", response_model=list[PurchaseRequestOut])
def list_requests(db: DbSession, actor: Participant):
    return [_present(actor, row, db) for row in service.list_requests(db, actor)]


@router.post("", response_model=PurchaseRequestOut, status_code=201)
def create_request(body: PurchaseRequestIn, db: DbSession, actor: Participant):
    request = service.create_request(
        db, actor, product_code=body.product_code, quantity=body.quantity, uom=body.uom,
        destination_pin=body.destination_pin, message=body.message, supplier_user_ids=body.supplier_user_ids,
    )
    db.commit()
    return _present(actor, request, db)


@router.get("/{request_id}", response_model=PurchaseRequestOut)
def get_request(request_id: uuid.UUID, db: DbSession, actor: Participant):
    return _present(actor, service.get_request(db, actor, request_id), db)


@router.put("/{request_id}/suppliers", response_model=PurchaseRequestOut)
def set_suppliers(request_id: uuid.UUID, body: SuppliersIn, db: DbSession, actor: Participant):
    request = service.set_suppliers(db, actor, request_id, body.supplier_user_ids)
    db.commit()
    return _present(actor, request, db)


@router.post("/{request_id}/send", response_model=PurchaseRequestOut)
def send_request(request_id: uuid.UUID, db: DbSession, actor: Participant):
    request = service.send_request(db, actor, request_id)
    db.commit()
    return _present(actor, request, db)


@router.post("/{request_id}/cancel", response_model=PurchaseRequestOut)
def cancel_request(request_id: uuid.UUID, db: DbSession, actor: Participant):
    request = service.cancel_request(db, actor, request_id)
    db.commit()
    return _present(actor, request, db)
