import pytest
from sqlalchemy import func, select

from app.models.negotiation import Negotiation
from app.models.order import Order
from app.orders import service as orders
from app.orders.constants import NEXT_STATUS, OrderStatus
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_orders import _negotiation, _place, product  # noqa: F401

REORDERS = "/api/v1/orders/reorder"


def _to(world, order, target: OrderStatus):
    status = OrderStatus(order.status)
    while status != target:
        status = NEXT_STATUS[status]
        orders.advance_order(world.session, world.actors["supplier"], order.id, to_status=status)
    world.session.flush()
    return order


def _ordered(client, world, product, status=OrderStatus.CONFIRMED):
    negotiation = _negotiation(world, product)
    placed = _place(client, world, negotiation)
    assert placed.status_code == 201, placed.text
    order = world.session.get(Order, placed.json()["id"])
    if status == OrderStatus.CANCELLED:
        orders.cancel_order(world.session, world.actors["buyer"], order.id, reason="No longer needed")
        world.session.flush()
    elif status != OrderStatus.PLACED:
        _to(world, order, status)
    _create(client, world, product, askingPrice="100.2500")
    return order


def test_previous_order_appears(client, world, product):
    order = _ordered(client, world, product, OrderStatus.DELIVERED)
    listed = client.get(REORDERS, headers=as_user(world, "buyer"))
    assert listed.status_code == 200, listed.text
    [row] = listed.json()
    assert row["orderNumber"] == order.order_number
    assert row["productCode"] == product.product_code
    assert row["supplierUserId"] == str(world.users["supplier"].id)
    assert row["quantity"] == "12000.5" and row["uom"] == "KG"
    assert row["previousPrice"] == {"amount": "98.7500", "currency": "INR"}
    assert row["currentAskingPrice"] == {"amount": "100.2500", "currency": "INR"}
    assert row["currentBenchmark"] == {"amount": "100.2500", "currency": "INR"}
    assert row["available"] is True and row["orderedAt"]


def test_cancelled_order_cannot_be_reordered(client, world, product):
    order = _ordered(client, world, product, OrderStatus.CANCELLED)
    before = world.session.scalar(select(func.count()).select_from(Negotiation))
    [row] = client.get(REORDERS, headers=as_user(world, "buyer")).json()
    assert row["orderStatus"] == "cancelled" and row["available"] is False
    assert row["unavailableReason"] == "cancelled"
    refused = client.post(f"/api/v1/orders/{order.id}/reorder", json={"quantity": "1000"}, headers=as_user(world, "buyer"))
    assert refused.status_code == 422
    assert refused.json()["error"]["details"]["reason"] == "cancelled"
    assert world.session.scalar(select(func.count()).select_from(Negotiation)) == before


@pytest.mark.parametrize("status", [OrderStatus.DELIVERED, OrderStatus.CONFIRMED, OrderStatus.PROCESSING])
def test_fulfilled_orders_are_eligible(client, world, product, status):
    order = _ordered(client, world, product, status)
    [row] = client.get(REORDERS, headers=as_user(world, "buyer")).json()
    assert row["orderId"] == str(order.id)
    assert row["orderStatus"] == status
    assert row["available"] is True


def test_inactive_product_or_supplier_is_unavailable(client, world, product):
    order = _ordered(client, world, product, OrderStatus.CONFIRMED)
    product.is_active = False
    world.session.flush()
    [hidden_product] = client.get(REORDERS, headers=as_user(world, "buyer")).json()
    assert hidden_product["available"] is False and hidden_product["unavailableReason"] == "inactive_product"
    refused = client.post(f"/api/v1/orders/{order.id}/reorder", json={"quantity": "1000"}, headers=as_user(world, "buyer"))
    assert refused.status_code == 422
    product.is_active = True
    world.users["supplier"].is_active = False
    world.session.flush()
    [hidden_supplier] = client.get(REORDERS, headers=as_user(world, "buyer")).json()
    assert hidden_supplier["available"] is False and hidden_supplier["unavailableReason"] == "inactive_supplier"
    assert client.post(
        f"/api/v1/orders/{order.id}/reorder", json={"quantity": "1000"}, headers=as_user(world, "buyer")
    ).status_code == 422


def test_reorder_creates_a_new_negotiation_at_the_current_asking_price(client, world, product):
    order = _ordered(client, world, product, OrderStatus.DELIVERED)
    orders_before = world.session.scalar(select(func.count()).select_from(Order))
    started = client.post(
        f"/api/v1/orders/{order.id}/reorder",
        json={"quantity": "8000", "destinationPin": "390020"},
        headers=as_user(world, "buyer"),
    )
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["offeredPrice"] == {"amount": "100.2500", "currency": "INR"}
    assert body["previousPrice"] == {"amount": "98.7500", "currency": "INR"}
    assert body["currentBenchmark"] == {"amount": "100.2500", "currency": "INR"}
    assert body["quantity"] == "8000" and body["freightStatus"] == "on_request"
    negotiation = world.session.get(Negotiation, body["negotiationId"])
    assert negotiation.id != order.negotiation_id
    assert negotiation.status == "open"
    assert negotiation.versions[0].offered_price != order.agreed_unit_price
    assert world.session.get(Order, order.id).agreed_unit_price == order.agreed_unit_price
    assert world.session.scalar(select(func.count()).select_from(Order)) == orders_before


def test_repeated_reorders_are_independent(client, world, product):
    order = _ordered(client, world, product, OrderStatus.PROCESSING)
    orders_before = world.session.scalar(select(func.count()).select_from(Order))
    first = client.post(f"/api/v1/orders/{order.id}/reorder", json={"quantity": "1000"}, headers=as_user(world, "buyer"))
    second = client.post(f"/api/v1/orders/{order.id}/reorder", json={"quantity": "2500"}, headers=as_user(world, "buyer"))
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["negotiationId"] != second.json()["negotiationId"]
    assert first.json()["quantity"] == "1000" and second.json()["quantity"] == "2500"
    assert world.session.scalar(select(func.count()).select_from(Order)) == orders_before
    stored = world.session.get(Order, order.id)
    assert stored.quantity == order.quantity and stored.agreed_unit_price == order.agreed_unit_price
