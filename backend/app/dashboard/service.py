"""Buyer dashboard assembled from existing order and negotiation services. Spend is agreed order totals only."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.identity.service import Actor
from app.negotiation.constants import NegotiationPermission, NegotiationStatus
from app.negotiation.service import allowed_actions, list_negotiations
from app.orders.constants import OrderPermission, OrderStatus
from app.orders.reorder import assess
from app.orders.service import list_orders

OPEN_NEGOTIATION = (NegotiationStatus.DRAFT, NegotiationStatus.OPEN, NegotiationStatus.COUNTERED)
CLOSED_ORDER = (OrderStatus.DELIVERED, OrderStatus.CANCELLED)


def _pending(actor: Actor, negotiation) -> bool:
    actions = allowed_actions(actor, negotiation)
    return bool(actions["offer"] or actions["accept"] or actions["reject"])


def buyer_dashboard(session: Session, actor: Actor) -> dict:
    actor.require(OrderPermission.PLACE)
    actor.require(NegotiationPermission.BUY)
    orders = list(list_orders(session, actor))
    negotiations = list(list_negotiations(session, actor))

    spend: dict[str, Decimal] = {}
    by_status: dict[str, int] = {}
    for order in orders:
        by_status[order.status] = by_status.get(order.status, 0) + 1
        if order.status == OrderStatus.CANCELLED:
            continue
        spend[order.currency] = spend.get(order.currency, Decimal("0")) + order.total_value

    recent_orders = sorted(orders, key=lambda order: order.updated_at, reverse=True)[:5]
    recent_negotiations = sorted(negotiations, key=lambda item: item.updated_at, reverse=True)[:5]
    return {
        "active_orders": sum(1 for order in orders if order.status not in CLOSED_ORDER),
        "open_negotiations": sum(1 for item in negotiations if item.status in OPEN_NEGOTIATION),
        "pending_actions": sum(1 for item in negotiations if _pending(actor, item)),
        "spend": [{"currency": currency, "amount": spend[currency]} for currency in sorted(spend)],
        "orders_by_status": by_status,
        "recent_orders": [_order_row(session, order) for order in recent_orders],
        "recent_negotiations": [_negotiation_row(item) for item in recent_negotiations],
    }


def _order_row(session: Session, order) -> dict:
    return {
        "kind": "order",
        "id": order.id,
        "reference": order.order_number,
        "product_name": order.product.name,
        "counterparty": order.supplier.organisation.name,
        "quantity": order.quantity,
        "uom": order.uom,
        "value": order.total_value,
        "value_kind": "order_total",
        "currency": order.currency,
        "status": order.status,
        "updated_at": order.updated_at,
        "can_reorder": assess(session, order)["available"],
    }


def _negotiation_row(negotiation) -> dict:
    latest = negotiation.versions[-1] if negotiation.versions else None
    return {
        "kind": "negotiation",
        "id": negotiation.id,
        "reference": negotiation.negotiation_number,
        "product_name": negotiation.product.name,
        "counterparty": negotiation.supplier.organisation.name,
        "quantity": latest.quantity if latest else negotiation.quantity,
        "uom": negotiation.uom,
        "value": latest.offered_price if latest else None,
        "value_kind": "offer",
        "currency": negotiation.currency,
        "status": negotiation.status,
        "updated_at": negotiation.updated_at,
        "can_reorder": False,
    }
