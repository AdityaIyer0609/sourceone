"""Orders placed from accepted negotiations. Buyers see their orders; suppliers see orders assigned to them."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.api.deps import DbSession, require_any
from app.api.v1.negotiations import party_out, quantity_text
from app.identity.service import Actor
from app.models.approval import OrderApproval
from app.models.order import Order
from app.orders import documents, reorder, service
from app.schemas.negotiation import RequirementOut
from app.orders.constants import FULFILMENT_FLOW, OrderPermission, OrderStatus
from app.schemas.order import (
    AgreedPriceOut,
    CancelOrderIn,
    CreateOrderIn,
    NegotiationRefOut,
    OrderActionsOut,
    DocumentReviewIn,
    OrderDocumentOut,
    OrderOut,
    OrderProductOut,
    ReorderIn,
    ReorderItemOut,
    ReorderOut,
    PodLinkOut,
    ShipmentOut,
    StatusChangeIn,
    StatusEventOut,
    TrackingOut,
    TrackingStepOut,
    ShipmentIn,
)
from app.pricing.charges import display_charges
from app.schemas.pricing import ChargeOut, Money

router = APIRouter(prefix="/orders", tags=["orders"])

Participant = Annotated[Actor, Depends(require_any(OrderPermission.PLACE, OrderPermission.FULFIL))]

STATUS_LABELS = {
    "placed": "Placed",
    "confirmed": "Confirmed",
    "processing": "Processing",
    "ready": "Ready",
    "dispatched": "Dispatched",
    "in_transit": "In transit",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def _shipment(order: Order) -> ShipmentOut:
    return ShipmentOut(
        lr_number=order.shipment_lr,
        transporter=order.shipment_transporter,
        vehicle=order.shipment_vehicle,
        eta=order.shipment_eta,
    )


def _pod(order: Order) -> PodLinkOut | None:
    pods = [document for document in documents.visible_documents(order) if document.document_type == "pod"]
    if not pods:
        return None
    document = pods[-1]
    return PodLinkOut(id=document.id, filename=document.filename, status=document.status)


def _tracking(actor: Actor, order: Order) -> TrackingOut:
    events = order.status_events
    reached = {e.to_status: e for e in events}
    shown = [*FULFILMENT_FLOW, *([OrderStatus.CANCELLED] if order.status == OrderStatus.CANCELLED else [])]
    steps = []
    for status in shown:
        event = reached.get(status)
        state = "current" if status == order.status else "completed" if event else "pending"
        steps.append(TrackingStepOut(
            status=status, label=STATUS_LABELS[status], state=state,
            at=event.created_at if event else None, note=event.note if event else None,
            changed_by=event.changed_by.full_name if event else None,
        ))
    can_progress = service.can_progress(actor, order)
    return TrackingOut(
        order_id=order.id,
        order_number=order.order_number,
        status=order.status,
        product=OrderProductOut(
            product_code=order.product.product_code, name=order.product.name, category=order.product.category
        ),
        quantity=quantity_text(order.quantity),
        uom=order.uom,
        buyer=party_out(order.buyer),
        supplier=party_out(order.supplier),
        viewer_role=service.role_of(actor, order),
        next_status=service.next_status(order) if can_progress else None,
        can_progress=can_progress,
        steps=steps,
        events=[
            StatusEventOut(
                from_status=e.from_status, to_status=e.to_status, changed_by=e.changed_by.full_name,
                changed_by_role="buyer" if e.changed_by_user_id == order.buyer_user_id else "supplier",
                note=e.note, created_at=e.created_at,
            )
            for e in events
        ],
        last_updated_at=events[-1].created_at if events else order.updated_at,
        shipment=_shipment(order),
        required_by=order.negotiation.required_by,
        delayed=service.is_delayed(order),
        pod=_pod(order),
    )


def _charges(order: Order) -> ChargeOut:
    freight = order.freight_amount if order.freight_status == "estimated" else None
    shown = display_charges(order.total_value, freight)
    return ChargeOut(
        material=Money(amount=f"{shown['material']:.4f}", currency=order.currency),
        freight=Money(amount=f"{shown['freight']:.4f}", currency=order.currency) if shown["freight"] is not None else None,
        gst_rate_percent=shown["gst_rate_percent"],
        gst_basis=shown["gst_basis"],
        gst=Money(amount=f"{shown['gst']:.4f}", currency=order.currency),
        payable=Money(amount=f"{shown['payable']:.4f}", currency=order.currency),
    )


def _present(actor: Actor, order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        product=OrderProductOut(
            product_code=order.product.product_code, name=order.product.name, category=order.product.category
        ),
        quantity=quantity_text(order.quantity),
        uom=order.uom,
        currency=order.currency,
        agreed_price=AgreedPriceOut(
            unit_price=Money(amount=f"{order.agreed_unit_price:.4f}", currency=order.currency), uom=order.uom
        ),
        total_value=Money(amount=f"{order.total_value:.2f}", currency=order.currency),
        charges=_charges(order),
        destination_pin=order.destination_pin,
        freight_status=order.freight_status,
        freight=Money(amount=f"{order.freight_amount:.4f}", currency=order.currency) if order.freight_amount is not None else None,
        freight_match=order.freight_match,
        negotiation=NegotiationRefOut(
            id=order.negotiation_id,
            negotiation_number=order.negotiation.negotiation_number,
            accepted_version_number=order.negotiation_version.version_number,
        ),
        buyer=party_out(order.buyer),
        supplier=party_out(order.supplier),
        viewer_role=service.role_of(actor, order),
        allowed_actions=OrderActionsOut(**service.allowed_actions(actor, order)),
        created_at=order.created_at,
        updated_at=order.updated_at,
        cancelled_at=order.cancelled_at,
        cancel_reason=order.cancel_reason,
        requirements=[RequirementOut(**row) for row in (order.requirements or [])],
        documents=[
            OrderDocumentOut(
                id=document.id, document_type=document.document_type, filename=document.filename,
                status=document.status, byte_size=document.byte_size,
            )
            for document in documents.visible_documents(order)
        ],
    )


@router.post("/from-negotiation/{negotiation_id}", response_model=None)
def create_from_negotiation(negotiation_id: uuid.UUID, body: CreateOrderIn, db: DbSession, actor: Participant):
    result = service.create_from_negotiation(
        db, actor, negotiation_id, destination_pin=body.destination_pin, freight_basis=body.freight_basis,
    )
    db.commit()
    if isinstance(result, OrderApproval):
        from app.api.v1.approvals import _present as present_approval
        return JSONResponse(status_code=202, content=present_approval(result).model_dump(mode="json", by_alias=True))
    presented = _present(actor, service.get_order(db, actor, result.id))
    return JSONResponse(status_code=201, content=presented.model_dump(mode="json", by_alias=True))


@router.get("", response_model=list[OrderOut])
def list_orders(db: DbSession, actor: Participant, status: OrderStatus | None = None):
    return [_present(actor, o) for o in service.list_orders(db, actor, status=status)]


def _money(amount, currency: str) -> Money:
    return Money(amount=f"{amount:.4f}", currency=currency)


def _reorder_item(item: dict) -> ReorderItemOut:
    order = item["order"]
    listing = item["listing"]
    return ReorderItemOut(
        order_id=order.id,
        order_number=order.order_number,
        order_status=order.status,
        product_code=order.product.product_code,
        product_name=order.product.name,
        supplier_user_id=order.supplier_user_id,
        supplier_name=order.supplier.full_name,
        organisation=order.supplier.organisation.name,
        organisation_id=order.supplier.organisation_id,
        quantity=quantity_text(order.quantity),
        uom=order.uom,
        currency=order.currency,
        previous_price=_money(order.agreed_unit_price, order.currency),
        ordered_at=order.created_at,
        available=item["available"],
        unavailable_reason=item["reason"],
        current_asking_price=_money(listing.asking_price, listing.currency) if listing else None,
        current_benchmark=_money(item["benchmark"], order.currency) if item["benchmark"] is not None else None,
    )


@router.get("/reorder", response_model=list[ReorderItemOut])
def list_reorders(db: DbSession, actor: Participant):
    return [_reorder_item(item) for item in reorder.list_reorderable(db, actor)]


@router.post("/{order_id}/reorder", response_model=ReorderOut, status_code=201)
def start_reorder(order_id: uuid.UUID, body: ReorderIn, db: DbSession, actor: Participant):
    result = reorder.start_reorder(
        db, actor, order_id, quantity=body.quantity, destination_pin=body.destination_pin,
    )
    db.commit()
    negotiation = result["negotiation"]
    item = result["item"]
    estimate = result["freight"]
    if estimate is None:
        freight_status = "not_requested"
        freight_amount = None
    elif estimate["freight"] is None:
        freight_status = "on_request"
        freight_amount = None
    else:
        freight_status = "estimated"
        freight_amount = estimate["freight"]
    order = item["order"]
    return ReorderOut(
        negotiation_id=negotiation.id,
        negotiation_number=negotiation.negotiation_number,
        quantity=quantity_text(negotiation.quantity),
        uom=negotiation.uom,
        offered_price=_money(negotiation.versions[0].offered_price, negotiation.currency),
        previous_price=_money(order.agreed_unit_price, order.currency),
        current_benchmark=_money(item["benchmark"], order.currency) if item["benchmark"] is not None else None,
        destination_pin=result["destination_pin"],
        freight_status=freight_status,
        freight=_money(freight_amount, order.currency) if freight_amount is not None else None,
        note="Opening offer is the current supplier asking price. The previous order price is not reused. Freight, when shown, is only an estimate.",
    )


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: uuid.UUID, db: DbSession, actor: Participant):
    return _present(actor, service.get_order(db, actor, order_id))


@router.get("/{order_id}/tracking", response_model=TrackingOut)
def get_tracking(order_id: uuid.UUID, db: DbSession, actor: Participant):
    return _tracking(actor, service.get_order(db, actor, order_id))


@router.post("/{order_id}/status", response_model=TrackingOut)
def change_status(order_id: uuid.UUID, body: StatusChangeIn, db: DbSession, actor: Participant):
    service.advance_order(
        db, actor, order_id, to_status=OrderStatus(body.to_status), note=body.note,
        lr_number=body.lr_number, transporter=body.transporter, vehicle=body.vehicle, eta=body.eta,
    )
    db.commit()
    return _tracking(actor, service.get_order(db, actor, order_id))


@router.post("/{order_id}/shipment", response_model=TrackingOut)
def record_shipment(order_id: uuid.UUID, body: ShipmentIn, db: DbSession, actor: Participant):
    service.save_shipment(
        db, actor, order_id, lr_number=body.lr_number, transporter=body.transporter,
        vehicle=body.vehicle, eta=body.eta,
    )
    db.commit()
    return _tracking(actor, service.get_order(db, actor, order_id))


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: uuid.UUID, db: DbSession, actor: Participant, body: CancelOrderIn | None = None):
    order = service.cancel_order(db, actor, order_id, reason=body.reason if body else None)
    db.commit()
    return _present(actor, order)


@router.post("/{order_id}/documents", response_model=OrderDocumentOut, status_code=201)
async def upload_order_document(
    order_id: uuid.UUID,
    db: DbSession,
    actor: Participant,
    documentType: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    content = await file.read()
    document = documents.save_document(
        db, actor, order_id, document_type=documentType, filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream", content=content,
    )
    db.commit()
    return OrderDocumentOut(
        id=document.id, document_type=document.document_type, filename=document.filename,
        status=document.status, byte_size=document.byte_size,
    )


@router.get("/{order_id}/documents/{document_id}/file")
def download_order_document(order_id: uuid.UUID, document_id: uuid.UUID, db: DbSession, actor: Participant):
    document, path = documents.open_document(db, actor, order_id, document_id)
    return FileResponse(path, media_type=document.content_type, filename=document.filename)


@router.post("/{order_id}/documents/{document_id}/review", response_model=OrderDocumentOut)
def review_order_document(
    order_id: uuid.UUID, document_id: uuid.UUID, body: DocumentReviewIn, db: DbSession, actor: Participant,
):
    document = documents.review_document(db, actor, order_id, document_id, status=body.status)
    db.commit()
    return OrderDocumentOut(
        id=document.id, document_type=document.document_type, filename=document.filename,
        status=document.status, byte_size=document.byte_size,
    )
