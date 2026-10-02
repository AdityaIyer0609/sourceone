"""Reorder starts a new negotiation from a past order. It never copies the old price and never places an order."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import utcnow
from app.catalogue import listings as catalogue_listings
from app.catalogue import market_average
from app.catalogue import products as catalogue
from app.core.errors import NotFound, ValidationFailed
from app.freight import service as freight
from app.identity.service import Actor
from app.models.identity import User
from app.models.listing import SupplierListing
from app.models.order import Order
from app.negotiation import service as negotiations
from app.negotiation.constants import NegotiationPermission
from app.orders.constants import OrderPermission, OrderStatus
from app.pricing import read_model, repository

ELIGIBLE_STATUSES = (
    OrderStatus.PLACED, OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
    OrderStatus.READY, OrderStatus.DISPATCHED, OrderStatus.DELIVERED,
)


def _orders(session: Session, actor: Actor):
    actor.require(OrderPermission.PLACE)
    return session.scalars(
        select(Order)
        .where(Order.buyer_user_id == actor.user_id)
        .options(
            selectinload(Order.product),
            selectinload(Order.supplier).selectinload(User.organisation),
        )
        .order_by(Order.created_at.desc(), Order.order_number.desc())
    ).all()


def _buyer_order(session: Session, actor: Actor, order_id: uuid.UUID) -> Order:
    order = next((row for row in _orders(session, actor) if row.id == order_id), None)
    if order is None:
        raise NotFound("Order not found", details={"orderId": str(order_id)})
    return order


def _listing(session: Session, order: Order) -> SupplierListing | None:
    rows = catalogue_listings.eligible_listings(session, order.product, currency=order.currency)
    return next((row for row in rows if row.supplier_user_id == order.supplier_user_id), None)


def _benchmark(session: Session, order: Order) -> tuple[Decimal | None, str | None]:
    if not order.product.is_active:
        return None, None
    product = catalogue.get_active_product(session, order.product.product_code)
    series = next((item for item in catalogue.buyer_series(product) if item.currency == order.currency), None)
    if series is None:
        return None, None
    average = market_average.current_average(session, product.id, order.currency)
    if average is not None:
        return average, series.code
    current = read_model.resolve_current(repository.timelines(session, [series.id]).get(series.id, []), utcnow())
    value = current.benchmark.value if current.benchmark is not None else None
    return value, series.code


def assess(session: Session, order: Order, *, hide_supplier: bool = False) -> dict:
    listing = None
    if order.status not in ELIGIBLE_STATUSES:
        reason = "cancelled"
    elif not order.product.is_active:
        reason = "inactive_product"
    elif hide_supplier:
        reason = None
    elif order.supplier is None:
        reason = "no_listing"
    elif not catalogue_listings.can_supply(session, order.supplier):
        reason = "inactive_supplier"
    else:
        listing = _listing(session, order)
        reason = None if listing is not None else "no_listing"
    benchmark, series_code = _benchmark(session, order)
    return {
        "order": order,
        "available": reason is None,
        "reason": reason,
        "listing": listing,
        "benchmark": benchmark,
        "series_code": series_code,
    }


def list_reorderable(session: Session, actor: Actor) -> list[dict]:
    from app.identity.privacy import suppliers_hidden
    hide = suppliers_hidden(actor)
    return [assess(session, order, hide_supplier=hide) for order in _orders(session, actor)]


def start_reorder(
    session: Session,
    actor: Actor,
    order_id: uuid.UUID,
    *,
    quantity: Decimal,
    destination_pin: str | None = None,
) -> dict:
    from app.core.errors import PermissionDenied
    from app.identity.privacy import suppliers_hidden
    if suppliers_hidden(actor):
        raise PermissionDenied("Place a new order for this product")
    actor.require(NegotiationPermission.BUY)
    if quantity <= 0:
        raise ValidationFailed("Quantity must be greater than zero", details={"quantity": str(quantity)})
    item = assess(session, _buyer_order(session, actor, order_id))
    if not item["available"]:
        raise ValidationFailed(
            "This order cannot be reordered",
            details={"reason": item["reason"], "orderId": str(order_id)},
        )
    order = item["order"]
    listing = item["listing"]
    freight_result = None
    pin = (destination_pin or "").strip() or None
    if pin:
        freight_result = freight.estimate(
            session, supplier_user_id=order.supplier_user_id, product_code=order.product.product_code,
            quantity=quantity, destination_pin=pin,
        )
    negotiation = negotiations.create_negotiation(
        session, actor, product_code=order.product.product_code, quantity=quantity,
        series_code=item["series_code"], currency=None if item["series_code"] else order.currency,
        offered_price=listing.asking_price, supplier_user_id=order.supplier_user_id,
        message=(
            f"Reorder of {order.order_number}. Opening offer is the supplier's current asking price, "
            "not the previous order price."
        ),
    )
    return {"negotiation": negotiation, "item": item, "freight": freight_result, "destination_pin": pin}
