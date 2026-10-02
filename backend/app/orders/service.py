"""Order V1. An order freezes the accepted negotiation's terms; it never reads current benchmarks."""

import re
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.catalogue import products as catalogue
from app.catalogue.listings import sellable_quantity, take_stock
from app.catalogue.specifications import requirement_snapshot
from app.core.clock import business_today, utcnow
from app.core.errors import DuplicateOrder, InvalidStateTransition, NotFound, OrderClosed, PermissionDenied, ValidationFailed
from app.freight import service as freight
from app.identity.service import Actor
from app.pricing.payment_terms import adjust_unit_price
from app.models.identity import User
from app.models.listing import SupplierListing
from app.models.negotiation import Negotiation, NegotiationVersion
from app.models.order import Order, OrderStatusEvent
from app.negotiation import service as negotiations
from app.negotiation.constants import NegotiationPermission, NegotiationStatus
from app.orders.constants import (
    CANCELLABLE_STATUSES,
    NEXT_STATUS,
    NUMBER_SEQUENCE,
    TERMINAL_STATUSES,
    OrderPermission,
    OrderStatus,
    SHIPMENT_STATUSES,
)

Role = Literal["buyer", "supplier"]
TOTAL_QUANTUM = Decimal("0.01")


def order_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return (quantity * unit_price).quantize(TOTAL_QUANTUM, rounding=ROUND_HALF_UP)


def role_of(actor: Actor, order: Order) -> Role | None:
    if actor.user_id == order.buyer_user_id and actor.has(OrderPermission.PLACE):
        return "buyer"
    if actor.user_id == order.supplier_user_id and actor.has(OrderPermission.FULFIL):
        return "supplier"
    return None


def allowed_actions(actor: Actor, order: Order) -> dict[str, bool]:
    return {"cancel": role_of(actor, order) is not None and order.status in CANCELLABLE_STATUSES}


def _next_number(session: Session, now: datetime) -> str:
    sequence = session.scalar(text(f"SELECT nextval('{NUMBER_SEQUENCE}')"))
    return f"SO-{business_today(now).year}-{sequence:04d}"


def _freight_snapshot(session: Session, negotiation: Negotiation, accepted, pin: str, freight_basis: str) -> dict:
    """Estimate only. The amount is never added to the negotiated order total."""
    try:
        result = freight.estimate(
            session,
            supplier_user_id=negotiation.supplier_user_id,
            product_code=negotiation.product.product_code,
            quantity=accepted.quantity,
            destination_pin=pin,
            include_distance=freight_basis == "distance",
        )
    except NotFound:
        return {"status": "on_request", "amount": None, "match": None}
    if freight_basis == "distance":
        estimated = result["distance_status"] == "estimated" and result["distance_freight"] is not None
        return {
            "status": "estimated" if estimated else "on_request",
            "amount": result["distance_freight"] if estimated else None,
            "match": "distance" if estimated else None,
        }
    estimated = result["freight"] is not None
    return {
        "status": "estimated" if estimated else "on_request",
        "amount": result["freight"] if estimated else None,
        "match": result["match"] if estimated else None,
    }


def place_for_assignment(
    session: Session, actor: Actor, *, product_code: str, quantity: Decimal, destination_pin: str,
    freight_basis: str = "standard", payment_terms: str | None = None, now: datetime | None = None,
) -> Order:
    """Buyer places an order at the current asking-price average. No supplier is attached yet."""
    from app.identity.privacy import suppliers_hidden
    if not suppliers_hidden(actor):
        raise ValidationFailed("Choose a supplier when placing this order")
    actor.require(OrderPermission.PLACE)
    if not actor.has(NegotiationPermission.BUY):
        raise PermissionDenied("Only a buyer can place an order")
    now = now or utcnow()
    product = catalogue.get_active_product(session, product_code)
    pin = destination_pin.strip()
    if not re.fullmatch(r"[1-9][0-9]{5}", pin):
        raise ValidationFailed("Delivery PIN must be 6 digits", details={"destinationPin": pin})
    if freight_basis not in ("standard", "distance"):
        raise ValidationFailed("Choose normal freight or road distance", details={"freightBasis": freight_basis})
    series = next((item for item in catalogue.buyer_series(product)), None)
    currency = series.currency if series is not None else "INR"
    from app.catalogue import market_average
    average = market_average.current_average(session, product.id, currency)
    if average is None:
        raise ValidationFailed("This product has no price yet")
    unit = adjust_unit_price(average, payment_terms)
    order = Order(
        order_number=_next_number(session, now),
        negotiation_id=None,
        negotiation_version_id=None,
        buyer_user_id=actor.user_id,
        supplier_user_id=None,
        product_id=product.id,
        quantity=quantity,
        uom=product.uom,
        currency=currency,
        agreed_unit_price=unit,
        total_value=order_total(quantity, unit),
        destination_pin=pin,
        freight_status="on_request",
        freight_amount=None,
        freight_match=None,
        requirements=requirement_snapshot(product),
        status=OrderStatus.PLACED,
        created_at=now,
        updated_at=now,
    )
    session.add(order)
    session.flush()
    _record_event(session, order, None, actor, note=None, now=now)
    return order


def assign_supplier(
    session: Session, actor: Actor, order_id: uuid.UUID, supplier_user_id: uuid.UUID, *, now: datetime | None = None,
) -> Order:
    """Admin attaches one supplier. The customer's price stays as placed. Stock moves here."""
    from app.identity.constants import IdentityPermission
    from app.identity.privacy import suppliers_hidden
    from app.pricing.constants import PricingPermission
    if suppliers_hidden(actor) or not (
        actor.has(IdentityPermission.MANAGE) or actor.has(PricingPermission.CONFIGURE) or actor.has(PricingPermission.PUBLISH)
    ):
        raise PermissionDenied("Only an admin can assign a supplier")
    now = now or utcnow()
    order = session.scalar(
        select(Order).where(Order.id == order_id).options(
            selectinload(Order.product), selectinload(Order.buyer),
        ).with_for_update()
    )
    if order is None:
        raise NotFound("Order not found", details={"orderId": str(order_id)})
    if order.supplier_user_id is not None or order.status != OrderStatus.PLACED:
        raise InvalidStateTransition("This order already has a supplier", details={"status": order.status})
    listing = session.scalar(
        select(SupplierListing).where(
            SupplierListing.supplier_user_id == supplier_user_id,
            SupplierListing.product_id == order.product_id,
            SupplierListing.is_active.is_(True),
        ).with_for_update()
    )
    if listing is None:
        raise NotFound("That supplier is not listing this product")
    if listing.sold_out:
        raise ValidationFailed("This supplier is sold out")
    if listing.maximum_quantity is not None and order.quantity > listing.maximum_quantity:
        raise ValidationFailed(
            "This supplier does not have that much left",
            details={"available": f"{listing.maximum_quantity.normalize():f}"},
        )
    buyer = Actor(user_id=order.buyer_user_id, permissions=frozenset({NegotiationPermission.BUY, OrderPermission.PLACE}))
    negotiation = negotiations.create_negotiation(
        session, buyer, product_code=order.product.product_code, quantity=order.quantity,
        supplier_user_id=supplier_user_id, destination_pin=order.destination_pin,
        currency=order.currency, now=now, message="Customer order.",
    )
    version = NegotiationVersion(
        negotiation_id=negotiation.id,
        version_number=1,
        created_by_user_id=order.buyer_user_id,
        offered_price=order.agreed_unit_price,
        currency=order.currency,
        quantity=order.quantity,
        uom=order.uom,
        message="Customer order.",
        created_at=now,
    )
    session.add(version)
    session.flush()
    negotiation.status = NegotiationStatus.OPEN
    negotiation.updated_at = now
    session.flush()
    negotiation.accepted_version_id = version.id
    negotiation.status = NegotiationStatus.ACCEPTED
    negotiation.closed_at = now
    negotiation.closed_by_user_id = order.buyer_user_id
    negotiation.updated_at = now
    session.flush()
    order.supplier_user_id = supplier_user_id
    order.negotiation_id = negotiation.id
    order.negotiation_version_id = version.id
    order.updated_at = now
    snapshot = _freight_snapshot(session, negotiation, version, order.destination_pin or "", "standard")
    order.freight_status = snapshot["status"]
    order.freight_amount = snapshot["amount"]
    order.freight_match = snapshot["match"]
    session.flush()
    take_stock(session, supplier_user_id, order.product_id, order.quantity)
    return order


def place_at_asking_price(
    session: Session, actor: Actor, *, product_code: str, supplier_user_id: uuid.UUID, quantity: Decimal,
    destination_pin: str, freight_basis: str = "standard", payment_terms: str | None = None, now: datetime | None = None,
) -> Order:
    """Buy the listing at its asking price. No counter-offer. Stock moves only if the order is created."""
    from app.identity.privacy import suppliers_hidden
    if suppliers_hidden(actor):
        raise PermissionDenied("Place the order for the product. A supplier is assigned afterwards.")
    actor.require(OrderPermission.PLACE)
    now = now or utcnow()
    product = catalogue.get_active_product(session, product_code)
    listing = session.scalar(
        select(SupplierListing).where(
            SupplierListing.supplier_user_id == supplier_user_id,
            SupplierListing.product_id == product.id,
            SupplierListing.is_active.is_(True),
        ).with_for_update()
    )
    if listing is None:
        raise NotFound("That supplier is not listing this product")
    if listing.sold_out:
        raise ValidationFailed("This supplier is sold out")
    if listing.availability == "on_request" or listing.maximum_quantity is None:
        raise ValidationFailed("This supplier has not confirmed stock. Ask them instead.")
    quantity = sellable_quantity(listing, quantity)
    if quantity < listing.minimum_quantity:
        raise ValidationFailed(
            "That quantity is outside what this supplier can sell now",
            details={"available": f"{listing.maximum_quantity.normalize():f}"},
        )
    negotiation = negotiations.create_negotiation(
        session, actor, product_code=product_code, quantity=quantity, supplier_user_id=supplier_user_id,
        destination_pin=destination_pin, freight_basis=freight_basis, payment_terms=payment_terms,
        currency=listing.currency, now=now,
    )
    version = NegotiationVersion(
        negotiation_id=negotiation.id,
        version_number=1,
        created_by_user_id=listing.supplier_user_id,
        offered_price=adjust_unit_price(listing.asking_price, payment_terms),
        currency=listing.currency,
        quantity=quantity,
        uom=listing.uom,
        message="Listed asking price.",
        created_at=now,
    )
    session.add(version)
    session.flush()
    negotiation.status = NegotiationStatus.OPEN
    negotiation.updated_at = now
    session.flush()
    negotiation.accepted_version_id = version.id
    negotiation.status = NegotiationStatus.ACCEPTED
    negotiation.closed_at = now
    negotiation.closed_by_user_id = actor.user_id
    negotiation.updated_at = now
    session.flush()
    return create_from_negotiation(
        session, actor, negotiation.id, destination_pin=destination_pin, freight_basis=freight_basis, now=now,
    )


def create_from_negotiation(
    session: Session, actor: Actor, negotiation_id: uuid.UUID, *, destination_pin: str,
    freight_basis: str = "standard", now: datetime | None = None,
) -> Order:
    from app.identity.privacy import suppliers_hidden
    if suppliers_hidden(actor):
        raise PermissionDenied("Place the order for the product. A supplier is assigned afterwards.")
    actor.require(OrderPermission.PLACE)
    now = now or utcnow()
    # Lock the listing before the negotiation so a second order cannot deadlock while stock is capped.
    preview = session.get(Negotiation, negotiation_id)
    if preview is not None:
        session.scalar(
            select(SupplierListing).where(
                SupplierListing.supplier_user_id == preview.supplier_user_id,
                SupplierListing.product_id == preview.product_id,
            ).with_for_update()
        )
    # Visibility and ownership come from the negotiation rules; only its buyer may place the order.
    negotiation = negotiations.get_negotiation(session, actor, negotiation_id, for_update=True)
    if negotiation.buyer_user_id != actor.user_id or not actor.has(NegotiationPermission.BUY):
        raise PermissionDenied("Only the buyer of this negotiation can place an order")
    if negotiation.status != NegotiationStatus.ACCEPTED:
        raise InvalidStateTransition(
            f"Only an accepted negotiation can become an order (this one is {negotiation.status})",
            details={"negotiationStatus": negotiation.status},
        )
    existing = session.scalar(select(Order).where(Order.negotiation_id == negotiation.id))
    if existing is not None:
        raise DuplicateOrder(
            f"Negotiation {negotiation.negotiation_number} already has order {existing.order_number}",
            details={"orderId": str(existing.id), "orderNumber": existing.order_number},
        )

    accepted = negotiations.negotiated_version(negotiation)
    listing = session.scalar(
        select(SupplierListing).where(
            SupplierListing.supplier_user_id == negotiation.supplier_user_id,
            SupplierListing.product_id == negotiation.product_id,
        )
    )
    if listing is not None and listing.sold_out:
        raise ValidationFailed("This supplier is sold out")
    quantity = sellable_quantity(listing, min(accepted.quantity, negotiation.quantity))
    if quantity <= 0:
        raise ValidationFailed("This supplier is sold out")
    pin = destination_pin.strip()
    if not re.fullmatch(r"[1-9][0-9]{5}", pin):
        raise ValidationFailed("Delivery PIN must be 6 digits", details={"destinationPin": pin})
    if freight_basis not in ("standard", "distance"):
        raise ValidationFailed("Choose normal freight or road distance", details={"freightBasis": freight_basis})
    return _insert_order(session, actor, negotiation, accepted, pin, freight_basis, now, quantity=quantity)


def _insert_order(session, actor, negotiation, accepted, pin: str, freight_basis: str, now: datetime, quantity: Decimal | None = None) -> Order:
    quantity = accepted.quantity if quantity is None else quantity
    freight_snapshot = _freight_snapshot(session, negotiation, accepted, pin, freight_basis)
    order = Order(
        order_number=_next_number(session, now),
        negotiation_id=negotiation.id,
        negotiation_version_id=accepted.id,
        buyer_user_id=negotiation.buyer_user_id,
        supplier_user_id=negotiation.supplier_user_id,
        product_id=negotiation.product_id,
        quantity=quantity,
        uom=accepted.uom,
        currency=accepted.currency,
        agreed_unit_price=accepted.offered_price,
        total_value=order_total(quantity, accepted.offered_price),
        destination_pin=pin,
        freight_status=freight_snapshot["status"],
        freight_amount=freight_snapshot["amount"],
        freight_match=freight_snapshot["match"],
        requirements=list(negotiation.requirements) if negotiation.requirements is not None else requirement_snapshot(negotiation.product),
        status=OrderStatus.PLACED,
        created_at=now,
        updated_at=now,
    )
    session.add(order)
    session.flush()
    take_stock(session, negotiation.supplier_user_id, negotiation.product_id, quantity)
    _record_event(session, order, None, actor, note=None, now=now)
    from app.purchase_requests.service import mark_converted
    mark_converted(session, negotiation.id)
    return order


def _record_event(
    session: Session, order: Order, from_status: str | None, actor: Actor, *, note: str | None, now: datetime
) -> OrderStatusEvent:
    """Call after the order's new status is flushed; the database checks the event continues the history."""
    latest = session.scalar(
        select(func.max(OrderStatusEvent.created_at)).where(OrderStatusEvent.order_id == order.id)
    )
    if latest is not None and now <= latest:
        now = latest + timedelta(microseconds=1)
    event = OrderStatusEvent(
        order_id=order.id, from_status=from_status, to_status=order.status, changed_by_user_id=actor.user_id,
        note=(note or "").strip() or None, created_at=now,
    )
    session.add(event)
    session.flush()
    session.expire(order, ["status_events"])
    return event


def next_status(order: Order) -> OrderStatus | None:
    return NEXT_STATUS.get(OrderStatus(order.status))


def can_progress(actor: Actor, order: Order) -> bool:
    return role_of(actor, order) == "supplier" and next_status(order) is not None


def _query():
    return select(Order).options(
        selectinload(Order.product),
        selectinload(Order.negotiation).selectinload(Negotiation.versions),
        selectinload(Order.negotiation_version),
        selectinload(Order.buyer).selectinload(User.organisation),
        selectinload(Order.supplier).selectinload(User.organisation),
        selectinload(Order.status_events).selectinload(OrderStatusEvent.changed_by),
        selectinload(Order.documents),
    )


def _visibility(actor: Actor):
    clauses = []
    if actor.has(OrderPermission.PLACE):
        clauses.append(Order.buyer_user_id == actor.user_id)
    if actor.has(OrderPermission.FULFIL):
        clauses.append(Order.supplier_user_id == actor.user_id)
    return or_(*clauses)


def list_orders(session: Session, actor: Actor, *, status: str | None = None) -> Sequence[Order]:
    actor.require(OrderPermission.PLACE, OrderPermission.FULFIL)
    stmt = _query().where(_visibility(actor)).order_by(Order.created_at.desc(), Order.order_number.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    return session.scalars(stmt).all()


def get_order(session: Session, actor: Actor, order_id: uuid.UUID, *, for_update: bool = False) -> Order:
    actor.require(OrderPermission.PLACE, OrderPermission.FULFIL)
    stmt = _query().where(Order.id == order_id, _visibility(actor))
    if for_update:
        stmt = stmt.with_for_update(of=Order)
    order = session.scalar(stmt)
    if order is None:
        raise NotFound("Order not found", details={"orderId": str(order_id)})
    return order


def _require_open(order: Order) -> None:
    if order.status in TERMINAL_STATUSES:
        raise OrderClosed(f"Order is {order.status} and can no longer change", details={"status": order.status})


def _clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if len(cleaned) > limit:
        raise ValidationFailed("That shipment detail is too long", details={"limit": limit})
    return cleaned


def _write_shipment(
    order: Order, *, lr_number: str | None, transporter: str | None, vehicle: str | None, eta: date | None,
) -> None:
    order.shipment_lr = _clean_text(lr_number, 40)
    order.shipment_transporter = _clean_text(transporter, 80)
    order.shipment_vehicle = _clean_text(vehicle, 40)
    order.shipment_eta = eta


def is_delayed(order: Order, *, today: date | None = None) -> bool:
    """Late only when a required date is stored, has passed, and the order is still open."""
    required = order.negotiation.required_by if order.negotiation is not None else None
    if required is None or order.status in TERMINAL_STATUSES:
        return False
    return (today or business_today()) > required


def advance_order(
    session: Session, actor: Actor, order_id: uuid.UUID, *, to_status: OrderStatus, note: str | None = None,
    now: datetime | None = None, lr_number: str | None = None, transporter: str | None = None,
    vehicle: str | None = None, eta: date | None = None,
) -> Order:
    """Supplier moves fulfilment forward exactly one step."""
    now = now or utcnow()
    order = get_order(session, actor, order_id, for_update=True)
    _require_open(order)
    if role_of(actor, order) != "supplier":
        raise PermissionDenied("Only the assigned supplier can update fulfilment status")
    if next_status(order) != to_status:
        raise InvalidStateTransition(
            f"Order cannot move from {order.status} to {to_status}",
            details={"from": order.status, "to": to_status, "next": next_status(order)},
        )
    recording = any(value not in (None, "") for value in (lr_number, transporter, vehicle, eta))
    if recording and to_status != OrderStatus.DISPATCHED:
        raise ValidationFailed("LR, transporter, vehicle, and ETA are saved when the order is marked dispatched")
    previous = order.status
    order.status = to_status
    if to_status == OrderStatus.DISPATCHED and recording:
        _write_shipment(order, lr_number=lr_number, transporter=transporter, vehicle=vehicle, eta=eta)
    order.updated_at = now
    session.flush()
    _record_event(session, order, previous, actor, note=note, now=now)
    return order


def save_shipment(
    session: Session, actor: Actor, order_id: uuid.UUID, *, lr_number: str | None, transporter: str | None,
    vehicle: str | None, eta: date | None, now: datetime | None = None,
) -> Order:
    """Supplier records facts already known. This does not move the status."""
    now = now or utcnow()
    order = get_order(session, actor, order_id, for_update=True)
    if role_of(actor, order) != "supplier":
        raise PermissionDenied("Only the assigned supplier can record shipment details")
    if order.status not in SHIPMENT_STATUSES:
        raise InvalidStateTransition(
            "Shipment details are recorded once the order is dispatched",
            details={"status": order.status},
        )
    _write_shipment(order, lr_number=lr_number, transporter=transporter, vehicle=vehicle, eta=eta)
    order.updated_at = now
    session.flush()
    return order


def cancel_order(
    session: Session, actor: Actor, order_id: uuid.UUID, *, reason: str | None = None, now: datetime | None = None
) -> Order:
    now = now or utcnow()
    order = get_order(session, actor, order_id, for_update=True)
    _require_open(order)
    if role_of(actor, order) is None:
        raise PermissionDenied("Only the buyer or assigned supplier can cancel this order")
    if order.status not in CANCELLABLE_STATUSES:
        raise InvalidStateTransition(
            f"An order that is {order.status} can no longer be cancelled",
            details={"from": order.status, "to": OrderStatus.CANCELLED},
        )
    previous = order.status
    order.status = OrderStatus.CANCELLED
    order.cancelled_at = now
    order.cancelled_by_user_id = actor.user_id
    order.cancel_reason = (reason or "").strip() or None
    order.updated_at = now
    session.flush()
    _record_event(session, order, previous, actor, note=order.cancel_reason, now=now)
    return order
