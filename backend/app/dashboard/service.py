"""Buyer dashboard assembled from this buyer's orders, negotiations, and requests.

Spend is the material order total. Freight and GST are not added.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.identity.service import Actor
from app.negotiation.constants import NegotiationPermission, NegotiationStatus
from app.negotiation.service import allowed_actions, awaiting_party, list_negotiations
from app.catalogue.listings import own_listings
from app.models.identity import User
from app.orders import documents as order_documents
from app.orders.approvals import list_approvals
from app.orders.constants import OrderPermission, OrderStatus
from app.orders.reorder import assess
from app.orders.service import list_orders
from app.purchase_requests.constants import RequestStatus
from app.purchase_requests.service import list_requests
from app.suppliers.service import _rates, performance

OPEN_NEGOTIATION = (NegotiationStatus.DRAFT, NegotiationStatus.OPEN, NegotiationStatus.COUNTERED)
OPEN_REQUEST = (RequestStatus.DRAFT, RequestStatus.SENT, RequestStatus.IN_NEGOTIATION)
CLOSED_ORDER = (OrderStatus.DELIVERED, OrderStatus.CANCELLED)
MATERIAL = Decimal("0.01")


def _pending(actor: Actor, negotiation) -> bool:
    actions = allowed_actions(actor, negotiation)
    return bool(actions["offer"] or actions["accept"] or actions["reject"])


def buyer_dashboard(session: Session, actor: Actor) -> dict:
    actor.require(OrderPermission.PLACE)
    actor.require(NegotiationPermission.BUY)
    orders = list(list_orders(session, actor))
    negotiations = list(list_negotiations(session, actor))
    requests = list(list_requests(session, actor))

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
        "open_requests": sum(1 for item in requests if item.status in OPEN_REQUEST),
        "pending_actions": sum(1 for item in negotiations if _pending(actor, item)),
        "spend": [{"currency": currency, "amount": spend[currency]} for currency in sorted(spend)],
        "spend_by_product": _slices(orders, lambda order: order.product.name),
        "spend_by_supplier": _slices(orders, lambda order: order.supplier.organisation.name),
        "variance": _variance(orders),
        "delivery": _delivery(orders),
        "suppliers": _suppliers(orders, negotiations),
        "alerts": _alerts(actor, session, orders, negotiations),
        "orders_by_status": by_status,
        "recent_orders": [_order_row(session, order) for order in recent_orders],
        "recent_negotiations": [_negotiation_row(item) for item in recent_negotiations],
    }


def _slices(orders, label_of) -> list[dict]:
    buckets: dict[tuple[str, str], dict] = {}
    for order in orders:
        if order.status == OrderStatus.CANCELLED:
            continue
        label = label_of(order)
        slot = buckets.setdefault((label, order.currency), {
            "label": label, "currency": order.currency, "amount": Decimal("0"), "order_count": 0,
        })
        slot["amount"] += order.total_value
        slot["order_count"] += 1
    return [buckets[key] for key in sorted(buckets)]


def _variance(orders) -> list[dict]:
    rows = []
    for order in orders:
        if order.status == OrderStatus.CANCELLED:
            continue
        snapshot = order.negotiation.benchmark_rate_snapshot
        if snapshot is None:
            continue
        difference = order.agreed_unit_price - snapshot
        rows.append({
            "order_id": order.id,
            "order_number": order.order_number,
            "product_name": order.product.name,
            "currency": order.currency,
            "agreed_unit_price": order.agreed_unit_price,
            "snapshot": snapshot,
            "unit_difference": difference.quantize(Decimal("0.0001")),
            "material_difference": (difference * order.quantity).quantize(MATERIAL, rounding=ROUND_HALF_UP),
        })
    return rows


def _delivery(orders) -> dict:
    on_time = 0
    delivered = 0
    for order in orders:
        required = order.negotiation.required_by
        if required is None or order.status != OrderStatus.DELIVERED:
            continue
        event = next((item for item in order.status_events if item.to_status == OrderStatus.DELIVERED), None)
        if event is None:
            continue
        delivered += 1
        if business_today(event.created_at) <= required:
            on_time += 1
    if delivered == 0:
        return {
            "available": False,
            "note": "No delivered order has a required date, so on-time delivery is not calculated.",
            "on_time": 0,
            "delivered": 0,
            "percent": None,
        }
    percent = (Decimal(on_time) * Decimal(100) / Decimal(delivered)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "available": True,
        "note": "Delivered on or before the required date stored on the negotiation.",
        "on_time": on_time,
        "delivered": delivered,
        "percent": f"{percent:.2f}",
    }


def _suppliers(orders, negotiations) -> list[dict]:
    groups: dict = {}
    for item in negotiations:
        org = item.supplier.organisation
        groups.setdefault(org.id, {"name": org.name, "negotiations": [], "orders": [], "documents": []})
        groups[org.id]["negotiations"].append(item)
    for order in orders:
        org = order.supplier.organisation
        bucket = groups.setdefault(org.id, {"name": org.name, "negotiations": [], "orders": [], "documents": []})
        bucket["orders"].append(order)
        bucket["documents"].extend(order.documents)
    panels = []
    for org_id, bucket in sorted(groups.items(), key=lambda pair: pair[1]["name"]):
        rates = _rates(bucket["negotiations"], bucket["orders"], bucket["documents"])
        panels.append({
            "organisation_id": org_id,
            "organisation": bucket["name"],
            "acceptance": rates["acceptance"],
            "order_cancellation": rates["order_cancellation"],
            "quality": rates["quality"],
            "response_time": rates["response_time"],
        })
    return panels


def _alerts(actor: Actor, session: Session, orders, negotiations) -> list[dict]:
    ordered = {order.negotiation_id for order in orders}
    waiting_approval = set()
    alerts = []
    for approval in list_approvals(session, actor):
        if approval.status != "pending":
            continue
        waiting_approval.add(approval.negotiation_id)
        if approval.submitted_by_user_id == actor.user_id:
            alerts.append({
                "kind": "approval",
                "id": approval.id,
                "title": f"Waiting for approval of {approval.negotiation.negotiation_number}",
                "detail": f"{approval.negotiation.product.name} · Material total",
            })
        elif actor.has(OrderPermission.APPROVE):
            alerts.append({
                "kind": "approval",
                "id": approval.id,
                "title": f"Approve {approval.negotiation.negotiation_number}",
                "detail": f"{approval.negotiation.product.name} · {approval.submitted_by.full_name}",
            })
    for item in negotiations:
        if item.status in OPEN_NEGOTIATION and awaiting_party(item) == "buyer":
            alerts.append({
                "kind": "negotiation",
                "id": item.id,
                "title": item.product.name,
                "detail": f"{item.negotiation_number} · Your turn to respond",
            })
        if item.status == NegotiationStatus.ACCEPTED and item.id not in ordered and item.id not in waiting_approval:
            alerts.append({
                "kind": "negotiation",
                "id": item.id,
                "title": f"Place the order for {item.product.name}",
                "detail": f"{item.negotiation_number} · Offer accepted",
            })
    return alerts


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


AWAITING_REQUEST = (RequestStatus.SENT, RequestStatus.IN_NEGOTIATION)


def _request_awaits(actor: Actor, request) -> bool:
    if request.status not in AWAITING_REQUEST:
        return False
    link = next((row for row in request.suppliers if row.supplier_user_id == actor.user_id), None)
    if link is None or link.negotiation is None:
        return False
    return awaiting_party(link.negotiation) == "supplier"


def supplier_dashboard(session: Session, actor: Actor) -> dict:
    """Work queued for this supplier. Counts are the same rows as the lists below."""
    actor.require(OrderPermission.FULFIL)
    actor.require(NegotiationPermission.SUPPLY)
    requests = [item for item in list_requests(session, actor) if _request_awaits(actor, item)]
    negotiations = [
        item for item in list_negotiations(session, actor)
        if item.status in OPEN_NEGOTIATION and awaiting_party(item) == "supplier"
    ]
    orders = [order for order in list_orders(session, actor) if order.status == OrderStatus.PLACED]
    listings = [
        row for row in own_listings(session, actor)
        if not row.is_active or row.availability == "on_request"
    ]
    documents = []
    for order in list_orders(session, actor):
        for document in order_documents.visible_documents(order):
            documents.append({
                "id": document.id,
                "order_id": order.id,
                "order_number": order.order_number,
                "document_type": document.document_type,
                "filename": document.filename,
                "status": document.status,
            })
    user = session.get(User, actor.user_id)
    rates = performance(session, user.organisation_id) if user is not None else _rates([], [])
    alerts = []
    for item in negotiations:
        alerts.append({
            "kind": "negotiation",
            "id": item.id,
            "title": item.product.name,
            "detail": f"{item.negotiation_number} · Your turn to respond",
        })
    for order in orders:
        alerts.append({
            "kind": "order",
            "id": order.id,
            "title": f"Confirm {order.order_number}",
            "detail": f"{order.product.name} · Waiting for you",
        })
    return {
        "open_requests": len(requests),
        "open_negotiations": len(negotiations),
        "orders_to_confirm": len(orders),
        "listings_to_review": len(listings),
        "requests": [{
            "id": item.id,
            "title": item.product.name,
            "detail": f"{item.request_number} · {item.buyer.organisation.name}",
        } for item in requests],
        "negotiations": [{
            "id": item.id,
            "title": item.product.name,
            "detail": f"{item.negotiation_number} · Your turn to respond",
        } for item in negotiations],
        "orders": [{
            "id": order.id,
            "title": order.order_number,
            "detail": f"{order.product.name} · Placed, waiting for confirmation",
        } for order in orders],
        "listings": [{
            "id": row.id,
            "product_code": row.product.product_code,
            "product_name": row.product.name,
            "availability": row.availability,
            "is_active": row.is_active,
            "asking_price": row.asking_price,
            "currency": row.currency,
        } for row in listings],
        "documents": documents,
        "performance": rates,
        "alerts": alerts,
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
