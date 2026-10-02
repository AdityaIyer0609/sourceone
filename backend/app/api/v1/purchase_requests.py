"""Purchase requests. Supplier replies happen on the negotiation this request opens."""

import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DbSession, require_any
from app.api.v1.negotiations import quantity_text
from app.catalogue.listings import supply_note
from app.models.listing import SupplierListing
from app.api.v1.pricing_presenters import money, quote_position
from app.catalogue import market_average
from app.identity.service import Actor
from app.models.purchase_request import PurchaseRequest
from app.negotiation import service as negotiations
from app.negotiation.constants import NegotiationPermission
from app.purchase_requests import service
from app.purchase_requests.constants import RequestStatus
from app.pricing.charges import display_charges
from app.schemas.negotiation import RequirementResponseOut
from app.schemas.pricing import ChargeOut, Money
from app.schemas.purchase_request import PurchaseRequestIn, PurchaseRequestOut, RequestSupplierOut, RequirementOut, SuppliersIn

router = APIRouter(prefix="/purchase-requests", tags=["purchase-requests"])

Participant = Annotated[Actor, Depends(require_any(NegotiationPermission.BUY, NegotiationPermission.SUPPLY))]


def _charges(material: Decimal, freight: Decimal | None, currency: str) -> ChargeOut:
    shown = display_charges(material, freight)
    return ChargeOut(
        material=Money(amount=f"{shown['material']:.4f}", currency=currency),
        freight=Money(amount=f"{shown['freight']:.4f}", currency=currency) if shown["freight"] is not None else None,
        gst_rate_percent=shown["gst_rate_percent"],
        gst_basis=shown["gst_basis"],
        gst=Money(amount=f"{shown['gst']:.4f}", currency=currency),
        payable=Money(amount=f"{shown['payable']:.4f}", currency=currency),
    )


def _value(amount: Decimal, currency: str) -> Money:
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Money(amount=f"{rounded:.4f}", currency=currency)


def _supply_note(db: DbSession, request: PurchaseRequest, supplier_user_id: uuid.UUID) -> str | None:
    listing = db.scalar(select(SupplierListing).where(
        SupplierListing.supplier_user_id == supplier_user_id,
        SupplierListing.product_id == request.product_id,
    ))
    if listing is None:
        return None
    return supply_note(listing, request.quantity)


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
        latest = negotiation.versions[-1] if negotiation and negotiation.versions else None
        unit = latest.offered_price if latest is not None else estimate["asking_price"]
        offer_currency = latest.currency if latest is not None else currency
        if negotiation is not None and negotiation.freight_status:
            freight_status = negotiation.freight_status
            freight_amount = negotiation.freight_amount
        else:
            freight_status = estimate["status"]
            freight_amount = estimate["freight"]
        material = _value(request.quantity * unit, offer_currency) if unit is not None and offer_currency else None
        landed = None
        charges = None
        if material is not None and offer_currency:
            freight_for_tax = freight_amount if freight_status == "estimated" else None
            charges = _charges(Decimal(material.amount), freight_for_tax, offer_currency)
            landed = _value(Decimal(charges.material.amount) + (freight_for_tax or 0), offer_currency) if freight_for_tax is not None else None
        suppliers.append(RequestSupplierOut(
            supplier_user_id=row.supplier_user_id,
            supplier_name=row.supplier.full_name,
            organisation=row.supplier.organisation.name,
            organisation_id=row.supplier.organisation_id,
            negotiation_id=negotiation.id if negotiation else None,
            negotiation_number=negotiation.negotiation_number if negotiation else None,
            negotiation_status=negotiation.status if negotiation else None,
            asking_price=money(estimate["asking_price"], currency) if estimate["asking_price"] is not None else None,
            latest_offer=money(unit, offer_currency) if unit is not None and offer_currency else None,
            material_value=material,
            freight_status=freight_status,
            freight=money(freight_amount, offer_currency or currency) if freight_amount is not None and (offer_currency or currency) else None,
            landed_estimate=landed,
            charges=charges,
            quote=quote_position(
                unit,
                negotiation.benchmark_rate_snapshot if negotiation is not None else None,
                market_average.current_average(db, request.product_id, offer_currency) if offer_currency else None,
                offer_currency,
            ),
            requirement_responses=[
                RequirementResponseOut(key=answer.requirement_key, status=answer.status, comment=answer.comment)
                for answer in (negotiations.requirement_answers(db, negotiation.id) if negotiation is not None else [])
            ],
            supply_note=_supply_note(db, request, row.supplier_user_id),
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
        freight_basis=request.freight_basis,
        required_by=request.required_by,
        payment_terms=request.payment_terms,
        requirements=[RequirementOut(**row) for row in request.requirements] if request.requirements is not None else None,
        message=request.message,
        offered_price=f"{request.offered_price:.4f}" if request.offered_price is not None else None,
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
        offered_price=body.offered_price,
        required_by=body.required_by, payment_terms=body.payment_terms, freight_basis=body.freight_basis,
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


@router.post("/{request_id}/suppliers/{supplier_user_id}/cancel", response_model=PurchaseRequestOut)
def cancel_supplier(request_id: uuid.UUID, supplier_user_id: uuid.UUID, db: DbSession, actor: Participant):
    request = service.cancel_supplier(db, actor, request_id, supplier_user_id)
    db.commit()
    return _present(actor, request, db)
