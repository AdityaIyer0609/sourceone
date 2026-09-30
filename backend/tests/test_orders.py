import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.catalogue import products as catalogue
from app.core.clock import business_today, utcnow
from app.core.errors import InvalidStateTransition, OrderClosed, PermissionDenied
from app.models.negotiation import Negotiation
from app.negotiation import service as negotiations
from app.orders import service
from app.orders.constants import OrderStatus
from app.pricing import service as pricing_service
from tests.test_api import _flatten, as_actor, as_user
from tests.test_negotiations import _other_buyer, _publish

ORDERS = "/api/v1/orders"


@pytest.fixture
def product(world):
    _publish(world, "99.40")
    item = catalogue.create_product(world.session, product_code=f"ORD-{world.suffix}", name="Orderable PP",
                                    category=f"cat-{world.suffix}", uom="KG")
    catalogue.map_rate_series(world.session, item, world.series["inr"])
    return item


def _negotiation(world, product, *, price="98.00", counter="98.75", quantity="12000.5", accept=True) -> Negotiation:
    buyer, supplier = world.actors["buyer"], world.actors["supplier"]
    negotiation = negotiations.create_negotiation(
        world.session, buyer, product_code=product.product_code, quantity=Decimal("12000"),
        offered_price=Decimal(price), supplier_user_id=world.users["supplier"].id,
    )
    negotiations.make_offer(world.session, supplier, negotiation.id, price=Decimal(counter), quantity=Decimal(quantity))
    if accept:
        negotiations.accept_offer(world.session, buyer, negotiation.id)
    return negotiation


def _place(client, world, negotiation, key="buyer", pin="560076"):
    return client.post(
        f"{ORDERS}/from-negotiation/{negotiation.id}",
        json={"destinationPin": pin, "freightBasis": "standard"},
        headers=as_user(world, key),
    )


def test_order_snapshots_accepted_terms_and_total(client, world, product):
    negotiation = _negotiation(world, product)
    response = _place(client, world, negotiation)
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["orderNumber"].startswith(f"SO-{business_today(utcnow()).year}-")
    assert order["status"] == "placed" and order["viewerRole"] == "buyer"
    assert order["product"] == {"productCode": product.product_code, "name": "Orderable PP", "category": product.category}
    assert order["quantity"] == "12000.5" and order["uom"] == "KG" and order["currency"] == "INR"
    assert order["agreedPrice"] == {"priceKind": "negotiated_price", "unitPrice": {"amount": "98.7500", "currency": "INR"},
                                    "uom": "KG"}
    # 12,000.5 kg x 98.75 = 1,185,049.375 -> rounded half-up to 1,185,049.38
    assert order["totalValue"] == {"amount": "1185049.38", "currency": "INR"}
    assert order["charges"]["material"]["amount"] == "1185049.3800"
    assert order["charges"]["gstRatePercent"] == 18
    assert order["charges"]["payable"]["amount"] != order["totalValue"]["amount"]
    assert order["agreedPrice"]["unitPrice"]["amount"] == "98.7500"
    assert order["destinationPin"] == "560076"
    assert order["freightStatus"] in ("estimated", "on_request")
    assert order["totalValue"]["amount"] != order.get("freight", {}).get("amount") if order.get("freight") else True
    assert order["negotiation"] == {"id": str(negotiation.id), "negotiationNumber": negotiation.negotiation_number,
                                    "acceptedVersionNumber": 2}
    assert order["createdAt"] and order["allowedActions"] == {"cancel": True}


def test_total_calculation_helper():
    assert service.order_total(Decimal("25000"), Decimal("1.1280")) == Decimal("28200.00")
    assert service.order_total(Decimal("0.333"), Decimal("3.0015")) == Decimal("1.00")


def test_only_accepted_negotiation_creates_order(client, world, product):
    open_negotiation = _negotiation(world, product, accept=False)
    response = _place(client, world, open_negotiation)
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    rejected = _negotiation(world, product, accept=False)
    negotiations.reject_offer(world.session, world.actors["buyer"], rejected.id)
    assert _place(client, world, rejected).status_code == 409

    with pytest.raises(DBAPIError, match="accepted"), world.session.begin_nested():
        world.session.execute(text(
            "INSERT INTO orders (id, order_number, negotiation_id, negotiation_version_id, buyer_user_id, "
            "supplier_user_id, product_id, quantity, uom, currency, agreed_unit_price, total_value, status) "
            "SELECT gen_random_uuid(), 'SO-TEST-X', n.id, v.id, n.buyer_user_id, n.supplier_user_id, n.product_id, "
            "v.quantity, v.uom, v.currency, v.offered_price, round(v.quantity * v.offered_price, 2), 'placed' "
            "FROM negotiations n JOIN negotiation_versions v ON v.negotiation_id = n.id WHERE n.id = :id LIMIT 1"
        ), {"id": open_negotiation.id})


def test_duplicate_order_prevented(client, world, product):
    negotiation = _negotiation(world, product)
    first = _place(client, world, negotiation).json()
    again = _place(client, world, negotiation)
    assert again.status_code == 409 and again.json()["error"]["code"] == "DUPLICATE_ORDER"
    assert again.json()["error"]["details"]["orderNumber"] == first["orderNumber"]
    client.post(f"{ORDERS}/{first['id']}/cancel", headers=as_user(world, "buyer"))
    assert _place(client, world, negotiation).json()["error"]["code"] == "DUPLICATE_ORDER"


def test_order_does_not_modify_negotiation(client, world, product):
    negotiation = _negotiation(world, product)
    before = client.get(f"/api/v1/negotiations/{negotiation.id}", headers=as_user(world, "buyer")).json()
    _place(client, world, negotiation)
    after = client.get(f"/api/v1/negotiations/{negotiation.id}", headers=as_user(world, "buyer")).json()
    assert after == before


def test_benchmark_changes_do_not_affect_order(client, world, product):
    order = _place(client, world, _negotiation(world, product)).json()
    newer = _publish(world, "120.00", days_ago=0)
    pricing_service.withdraw_benchmark(world.session, world.actors["bob"], newer.id, reason="Revised")
    again = client.get(f"{ORDERS}/{order['id']}", headers=as_user(world, "buyer")).json()
    assert again["agreedPrice"] == order["agreedPrice"] and again["totalValue"] == order["totalValue"]


def test_access_control(client, world, product):
    negotiation = _negotiation(world, product)
    assert _place(client, world, negotiation, key="supplier").status_code == 403
    other = _other_buyer(world)
    stranger = client.post(
        f"{ORDERS}/from-negotiation/{negotiation.id}",
        json={"destinationPin": "560076"},
        headers=as_actor(other),
    )
    assert stranger.status_code == 404

    order = _place(client, world, negotiation).json()
    assert client.get(f"{ORDERS}/{order['id']}", headers=as_actor(other)).status_code == 404
    assert order["id"] not in [o["id"] for o in client.get(ORDERS, headers=as_actor(other)).json()]
    supplier = client.get(f"{ORDERS}/{order['id']}", headers=as_user(world, "supplier"))
    assert supplier.status_code == 200 and supplier.json()["viewerRole"] == "supplier"
    assert order["id"] in [o["id"] for o in client.get(ORDERS, headers=as_user(world, "supplier")).json()]
    assert client.get(ORDERS, headers=as_user(world, "alice")).status_code == 403
    assert client.get(ORDERS).status_code == 401


def test_cancellation_rules(client, world, product):
    buyer_cancel = _place(client, world, _negotiation(world, product)).json()
    cancelled = client.post(f"{ORDERS}/{buyer_cancel['id']}/cancel", json={"reason": "Plan changed"},
                            headers=as_user(world, "buyer"))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled" and cancelled.json()["cancelReason"] == "Plan changed"
    assert cancelled.json()["cancelledAt"] and cancelled.json()["allowedActions"] == {"cancel": False}

    confirmed = _place(client, world, _negotiation(world, product)).json()
    service.advance_order(world.session, world.actors["supplier"], uuid.UUID(confirmed["id"]), to_status=OrderStatus.CONFIRMED)
    by_supplier = client.post(f"{ORDERS}/{confirmed['id']}/cancel", headers=as_user(world, "supplier"))
    assert by_supplier.status_code == 200 and by_supplier.json()["status"] == "cancelled"

    processing = _place(client, world, _negotiation(world, product)).json()
    for status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING):
        service.advance_order(world.session, world.actors["supplier"], uuid.UUID(processing["id"]), to_status=status)
    late = client.post(f"{ORDERS}/{processing['id']}/cancel", headers=as_user(world, "buyer"))
    assert late.status_code == 409 and late.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_invalid_status_transitions(client, world, product):
    order_id = uuid.UUID(_place(client, world, _negotiation(world, product)).json()["id"])
    supplier, buyer = world.actors["supplier"], world.actors["buyer"]
    with pytest.raises(InvalidStateTransition):
        service.advance_order(world.session, supplier, order_id, to_status=OrderStatus.PROCESSING)
    with pytest.raises(PermissionDenied):
        service.advance_order(world.session, buyer, order_id, to_status=OrderStatus.CONFIRMED)
    service.advance_order(world.session, supplier, order_id, to_status=OrderStatus.CONFIRMED)
    with pytest.raises(InvalidStateTransition):
        service.advance_order(world.session, supplier, order_id, to_status=OrderStatus.PLACED)
    with pytest.raises(DBAPIError, match="cannot move"), world.session.begin_nested():
        world.session.execute(text("UPDATE orders SET status = 'delivered' WHERE id = :id"), {"id": order_id})
    with pytest.raises(DBAPIError, match="immutable"), world.session.begin_nested():
        world.session.execute(text("UPDATE orders SET agreed_unit_price = 1, total_value = round(quantity, 2) "
                                   "WHERE id = :id"), {"id": order_id})


@pytest.mark.parametrize("final", [OrderStatus.DELIVERED, OrderStatus.CANCELLED])
def test_terminal_orders_cannot_change(client, world, product, final):
    order_id = uuid.UUID(_place(client, world, _negotiation(world, product)).json()["id"])
    supplier = world.actors["supplier"]
    if final == OrderStatus.CANCELLED:
        service.cancel_order(world.session, world.actors["buyer"], order_id)
    else:
        for status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.READY, OrderStatus.DISPATCHED,
                       OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED):
            service.advance_order(world.session, supplier, order_id, to_status=status)
    again = client.post(f"{ORDERS}/{order_id}/cancel", headers=as_user(world, "buyer"))
    assert again.status_code == 409 and again.json()["error"]["code"] == "ORDER_CLOSED"
    with pytest.raises(OrderClosed):
        service.advance_order(world.session, supplier, order_id, to_status=OrderStatus.CONFIRMED)
    with pytest.raises(DBAPIError, match="final"), world.session.begin_nested():
        world.session.execute(text("UPDATE orders SET cancel_reason = 'x' WHERE id = :id"), {"id": order_id})
    with pytest.raises(DBAPIError, match="cannot be deleted"), world.session.begin_nested():
        world.session.execute(text("DELETE FROM orders WHERE id = :id"), {"id": order_id})


def test_order_response_has_no_pricing_source_data(client, world, product):
    world.ingest(business_today(utcnow()) - timedelta(days=2), [world.row(1, "99.40"), world.row(2, "99.00", producer="B")])
    order = _place(client, world, _negotiation(world, product)).json()
    for key in ("buyer", "supplier"):
        for payload in (client.get(f"{ORDERS}/{order['id']}", headers=as_user(world, key)).json(),
                        client.get(ORDERS, headers=as_user(world, key)).json()):
            keys, values = _flatten(payload)
            assert not [k for k in keys if any(w in k.lower() for w in ("producer", "source", "benchmark", "series"))]
            forbidden = {p.code for p in world.producers.values()} | {p.name for p in world.producers.values()}
            forbidden |= {world.erp_source.code, world.manual_source.code, world.series["inr"].code, "RAF-1", "Plant"}
            assert not [v for v in values if any(f in v for f in forbidden)]
