"""Purchase requests. Sending one opens negotiations through the existing negotiation service."""

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.catalogue import listings as catalogue_listings
from app.catalogue import products as catalogue
from app.catalogue.specifications import requirement_snapshot
from app.core.clock import business_today, utcnow
from app.core.errors import InvalidStateTransition, NotFound, PermissionDenied, ValidationFailed
from app.freight import service as freight
from app.identity.service import Actor
from app.models.identity import User
from app.models.negotiation import Negotiation
from app.models.order import Order
from app.models.purchase_request import PurchaseRequest, PurchaseRequestSupplier
from app.negotiation import service as negotiations
from app.negotiation.constants import NegotiationPermission, NegotiationStatus
from app.purchase_requests.constants import NUMBER_SEQUENCE, RequestStatus

OPEN_FOR_CANCEL = (RequestStatus.DRAFT, RequestStatus.SENT, RequestStatus.IN_NEGOTIATION)


def _next_number(session: Session, now: datetime) -> str:
    sequence = session.scalar(text(f"SELECT nextval('{NUMBER_SEQUENCE}')"))
    return f"RFQ-{business_today(now).year}-{sequence:04d}"


def _query():
    return select(PurchaseRequest).options(
        selectinload(PurchaseRequest.buyer).selectinload(User.organisation),
        selectinload(PurchaseRequest.product),
        selectinload(PurchaseRequest.suppliers).selectinload(PurchaseRequestSupplier.supplier).selectinload(User.organisation),
        selectinload(PurchaseRequest.suppliers).selectinload(PurchaseRequestSupplier.negotiation).selectinload(Negotiation.versions),
    )


def _visibility(actor: Actor):
    clauses = []
    if actor.has(NegotiationPermission.BUY):
        clauses.append(PurchaseRequest.buyer_user_id == actor.user_id)
    if actor.has(NegotiationPermission.SUPPLY):
        clauses.append(
            PurchaseRequest.suppliers.any(PurchaseRequestSupplier.supplier_user_id == actor.user_id)
            & (PurchaseRequest.status != RequestStatus.DRAFT)
        )
    return or_(*clauses)


def _supplier_moved(negotiation: Negotiation) -> bool:
    if negotiation.status in (NegotiationStatus.COUNTERED, NegotiationStatus.ACCEPTED, NegotiationStatus.REJECTED):
        return True
    return any(version.created_by_user_id == negotiation.supplier_user_id for version in negotiation.versions)


def sync_status(session: Session, request: PurchaseRequest) -> PurchaseRequest:
    """Keep the stored status aligned with the negotiations and order this request already opened."""
    if request.status == RequestStatus.CANCELLED:
        return request
    negotiation_ids = [row.negotiation_id for row in request.suppliers if row.negotiation_id]
    converted = bool(negotiation_ids) and session.scalar(
        select(Order.id).where(Order.negotiation_id.in_(negotiation_ids))
    ) is not None
    if converted:
        request.status = RequestStatus.CONVERTED
    elif any(row.negotiation and _supplier_moved(row.negotiation) for row in request.suppliers):
        request.status = RequestStatus.IN_NEGOTIATION
    elif negotiation_ids:
        request.status = RequestStatus.SENT
    else:
        request.status = RequestStatus.DRAFT
    session.flush()
    return request


def mark_converted(session: Session, negotiation_id: uuid.UUID) -> None:
    row = session.scalar(
        select(PurchaseRequestSupplier)
        .where(PurchaseRequestSupplier.negotiation_id == negotiation_id)
        .options(selectinload(PurchaseRequestSupplier.request))
    )
    if row is not None and row.request.status != RequestStatus.CANCELLED:
        row.request.status = RequestStatus.CONVERTED
        session.flush()


def get_request(session: Session, actor: Actor, request_id: uuid.UUID) -> PurchaseRequest:
    actor.require(NegotiationPermission.BUY, NegotiationPermission.SUPPLY)
    request = session.scalar(_query().where(PurchaseRequest.id == request_id, _visibility(actor)))
    if request is None:
        raise NotFound("Purchase request not found", details={"requestId": str(request_id)})
    return sync_status(session, request)


def list_requests(session: Session, actor: Actor) -> Sequence[PurchaseRequest]:
    actor.require(NegotiationPermission.BUY, NegotiationPermission.SUPPLY)
    rows = session.scalars(_query().where(_visibility(actor)).order_by(PurchaseRequest.created_at.desc())).all()
    return [sync_status(session, row) for row in rows]


def _listing_for(session: Session, product, supplier_user_id: uuid.UUID):
    return next(
        (row for row in catalogue_listings.eligible_listings(session, product) if row.supplier_user_id == supplier_user_id),
        None,
    )


def _replace_suppliers(session: Session, request: PurchaseRequest, supplier_user_ids: list[uuid.UUID]) -> None:
    product = request.product
    chosen = []
    for supplier_user_id in dict.fromkeys(supplier_user_ids):
        if supplier_user_id == request.buyer_user_id:
            raise ValidationFailed("Buyer and supplier must be different users", details={"supplierUserId": str(supplier_user_id)})
        if _listing_for(session, product, supplier_user_id) is None:
            raise ValidationFailed(
                "Choose a supplier with an active listing for this product",
                details={"supplierUserId": str(supplier_user_id)},
            )
        chosen.append(supplier_user_id)
    request.suppliers.clear()
    session.flush()
    for supplier_user_id in chosen:
        request.suppliers.append(PurchaseRequestSupplier(supplier_user_id=supplier_user_id))
    session.flush()


def create_request(
    session: Session,
    actor: Actor,
    *,
    product_code: str,
    quantity: Decimal,
    uom: str,
    destination_pin: str,
    message: str | None,
    supplier_user_ids: list[uuid.UUID],
    offered_price: Decimal | None = None,
    required_by: date | None = None,
    payment_terms: str | None = None,
    freight_basis: str = "standard",
    now: datetime | None = None,
) -> PurchaseRequest:
    actor.require(NegotiationPermission.BUY)
    now = now or utcnow()
    if quantity <= 0:
        raise ValidationFailed("Quantity must be greater than zero", details={"quantity": str(quantity)})
    product = catalogue.get_active_product(session, product_code)
    if uom.strip().upper() != product.uom:
        raise ValidationFailed(
            f"This product is bought in {product.uom}",
            details={"uom": product.uom},
        )
    if freight_basis not in ("standard", "distance"):
        raise ValidationFailed("Choose normal freight or road distance", details={"freightBasis": freight_basis})
    terms = (payment_terms or "").strip() or None
    if terms is not None and len(terms) > 120:
        raise ValidationFailed("Payment terms are too long", details={"field": "paymentTerms"})
    request = PurchaseRequest(
        request_number=_next_number(session, now),
        buyer_user_id=actor.user_id,
        product_id=product.id,
        quantity=quantity,
        uom=product.uom,
        destination_pin=freight._pin(destination_pin, "destinationPin"),
        freight_basis=freight_basis,
        required_by=required_by,
        payment_terms=terms,
        requirements=requirement_snapshot(product),
        message=(message or "").strip() or None,
        offered_price=offered_price,
        status=RequestStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    session.add(request)
    session.flush()
    request.product = product
    if supplier_user_ids:
        _replace_suppliers(session, request, supplier_user_ids)
    return get_request(session, actor, request.id)


def set_suppliers(session: Session, actor: Actor, request_id: uuid.UUID, supplier_user_ids: list[uuid.UUID]) -> PurchaseRequest:
    request = get_request(session, actor, request_id)
    if request.buyer_user_id != actor.user_id:
        raise PermissionDenied("Only the buyer can choose suppliers")
    if request.status != RequestStatus.DRAFT:
        raise InvalidStateTransition("Suppliers can only be changed before the request is sent", details={"status": request.status})
    if not supplier_user_ids:
        raise ValidationFailed("Choose at least one supplier", details={"field": "supplierUserIds"})
    _replace_suppliers(session, request, supplier_user_ids)
    return get_request(session, actor, request.id)


def send_request(session: Session, actor: Actor, request_id: uuid.UUID) -> PurchaseRequest:
    """Open one negotiation per selected supplier. This does not create an order."""
    request = get_request(session, actor, request_id)
    if request.buyer_user_id != actor.user_id:
        raise PermissionDenied("Only the buyer can send a purchase request")
    if request.status != RequestStatus.DRAFT:
        raise InvalidStateTransition("Only a draft purchase request can be sent", details={"status": request.status})
    if not request.suppliers:
        raise ValidationFailed("Choose a supplier before sending", details={"field": "supplierUserIds"})
    product = request.product
    series_by_currency = {series.currency: series for series in catalogue.buyer_series(product)}
    for row in request.suppliers:
        listing = _listing_for(session, product, row.supplier_user_id)
        if listing is None:
            raise ValidationFailed(
                "A selected supplier is no longer listing this product",
                details={"supplierUserId": str(row.supplier_user_id)},
            )
        series = series_by_currency.get(listing.currency)
        negotiation = negotiations.create_negotiation(
            session,
            actor,
            product_code=product.product_code,
            quantity=request.quantity,
            series_code=series.code if series else None,
            currency=None if series else listing.currency,
            offered_price=request.offered_price if request.offered_price is not None else listing.asking_price,
            supplier_user_id=row.supplier_user_id,
            message=request.message or f"Purchase request {request.request_number}.",
            destination_pin=request.destination_pin,
            freight_basis=request.freight_basis,
            required_by=request.required_by,
            payment_terms=request.payment_terms,
            requirements=request.requirements,
        )
        row.negotiation_id = negotiation.id
        row.negotiation = negotiation
    request.status = RequestStatus.SENT
    session.flush()
    session.expire(request, ["suppliers"])
    return get_request(session, actor, request.id)


def cancel_request(session: Session, actor: Actor, request_id: uuid.UUID, *, now: datetime | None = None) -> PurchaseRequest:
    now = now or utcnow()
    request = get_request(session, actor, request_id)
    if request.buyer_user_id != actor.user_id:
        raise PermissionDenied("Only the buyer can cancel a purchase request")
    if request.status not in OPEN_FOR_CANCEL:
        raise InvalidStateTransition(
            f"A {request.status.replace('_', ' ')} purchase request cannot be cancelled",
            details={"status": request.status},
        )
    for row in request.suppliers:
        if row.negotiation is None:
            continue
        if row.negotiation.status == NegotiationStatus.ACCEPTED:
            raise InvalidStateTransition(
                "An accepted negotiation continues into the order flow and cannot be cancelled from the request",
                details={"negotiationId": str(row.negotiation.id)},
            )
        if row.negotiation.status not in (NegotiationStatus.CANCELLED, NegotiationStatus.REJECTED):
            negotiations.cancel_negotiation(
                session, actor, row.negotiation.id, reason=f"Purchase request {request.request_number} cancelled", now=now,
            )
    request.status = RequestStatus.CANCELLED
    request.cancelled_at = now
    session.flush()
    return get_request(session, actor, request.id)


def cancel_supplier(
    session: Session, actor: Actor, request_id: uuid.UUID, supplier_user_id: uuid.UUID, *, now: datetime | None = None,
) -> PurchaseRequest:
    """Close one supplier's negotiation. The request stays open while another supplier is still in it."""
    now = now or utcnow()
    request = get_request(session, actor, request_id)
    if request.buyer_user_id != actor.user_id:
        raise PermissionDenied("Only the buyer can cancel a supplier on this request")
    if request.status not in OPEN_FOR_CANCEL:
        raise InvalidStateTransition(
            f"A {request.status.replace('_', ' ')} purchase request cannot be cancelled",
            details={"status": request.status},
        )
    row = next((item for item in request.suppliers if item.supplier_user_id == supplier_user_id), None)
    if row is None:
        raise NotFound("That supplier is not on this request")
    if row.negotiation is None:
        raise ValidationFailed("This supplier has not been sent a negotiation")
    if row.negotiation.status == NegotiationStatus.ACCEPTED:
        raise InvalidStateTransition(
            "An accepted negotiation continues into the order flow and cannot be cancelled from the request",
            details={"negotiationId": str(row.negotiation.id)},
        )
    if row.negotiation.status not in (NegotiationStatus.CANCELLED, NegotiationStatus.REJECTED):
        negotiations.cancel_negotiation(
            session, actor, row.negotiation.id, reason=f"Purchase request {request.request_number} cancelled for this supplier", now=now,
        )
    talks = [item.negotiation for item in request.suppliers if item.negotiation is not None]
    still_open = [item for item in talks if item.status not in (NegotiationStatus.CANCELLED, NegotiationStatus.REJECTED)]
    if talks and not still_open:
        request.status = RequestStatus.CANCELLED
        request.cancelled_at = now
        session.flush()
        return get_request(session, actor, request.id)
    return sync_status(session, request)


def freight_for(session: Session, request: PurchaseRequest, supplier_user_id: uuid.UUID) -> dict:
    try:
        result = freight.estimate(
            session,
            supplier_user_id=supplier_user_id,
            product_code=request.product.product_code,
            quantity=request.quantity,
            destination_pin=request.destination_pin,
        )
    except (NotFound, ValidationFailed):
        return {"status": "on_request", "freight": None, "asking_price": None, "currency": None}
    listing = result["listing"]
    return {
        "status": "estimated" if result["freight"] is not None else "on_request",
        "freight": result["freight"],
        "asking_price": listing.asking_price,
        "currency": listing.currency,
    }
