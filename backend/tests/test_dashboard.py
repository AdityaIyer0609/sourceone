from decimal import Decimal

from app.catalogue import products as catalogue
from app.models.order import Order
from app.orders.constants import OrderStatus
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_negotiations import _offer, _start
from tests.test_orders import _negotiation, _place, product  # noqa: F401
from tests.test_reorder import _to

DASHBOARD = "/api/v1/dashboard"


def test_dashboard_with_no_activity(client, world):
    body = client.get(DASHBOARD, headers=as_user(world, "buyer")).json()
    assert body["activeOrders"] == 0
    assert body["openNegotiations"] == 0
    assert body["pendingActions"] == 0
    assert body["spend"] == []
    assert body["ordersByStatus"] == {}
    assert body["recentOrders"] == [] and body["recentNegotiations"] == []


def test_dashboard_orders_spend_and_recent_status(client, world, product):
    negotiation = _negotiation(world, product)
    placed = _place(client, world, negotiation)
    assert placed.status_code == 201, placed.text
    order = placed.json()
    _create(client, world, product, askingPrice="100.2500")
    stored = world.session.get(Order, order["id"])
    _to(world, stored, OrderStatus.PROCESSING)

    body = client.get(DASHBOARD, headers=as_user(world, "buyer")).json()
    assert body["activeOrders"] == 1
    assert body["ordersByStatus"] == {"processing": 1}
    assert body["spend"] == [{"currency": "INR", "amount": order["totalValue"]["amount"]}]
    assert order["agreedPrice"]["unitPrice"]["amount"] == "98.7500"
    assert body["spend"][0]["amount"] != f"{(Decimal('12000.5') * Decimal('99.40')):.2f}"
    [recent] = body["recentOrders"]
    assert recent["reference"] == order["orderNumber"]
    assert recent["status"] == "processing"
    assert recent["valueKind"] == "order_total"
    assert recent["value"] == {"amount": order["totalValue"]["amount"], "currency": "INR"}
    assert recent["canReorder"] is True


def test_spend_keeps_currencies_separate_and_skips_cancelled(client, world, product):
    kept = _place(client, world, _negotiation(world, product)).json()
    cancelled_negotiation = _negotiation(world, product, price="90.00", counter="90.00")
    cancelled = _place(client, world, cancelled_negotiation)
    assert client.post(f"/api/v1/orders/{cancelled.json()['id']}/cancel", headers=as_user(world, "buyer")).status_code == 200

    usd = catalogue.create_product(
        world.session, product_code=f"USD-{world.suffix}", name="Imported PP", category=product.category, uom="KG",
    )
    catalogue.map_rate_series(world.session, usd, world.series["usd"])
    world.session.flush()
    started = client.post("/api/v1/negotiations", json={
        "productCode": usd.product_code, "seriesCode": world.series["usd"].code, "quantity": "100",
        "offeredPrice": "1.1000", "supplierUserId": str(world.users["supplier"].id),
    }, headers=as_user(world, "buyer"))
    assert started.status_code == 201, started.text
    countered = _offer(client, world, "supplier", started.json()["id"], "1.2000", quantity="100")
    assert countered.status_code == 201, countered.text
    assert client.post(f"/api/v1/negotiations/{started.json()['id']}/accept", headers=as_user(world, "buyer")).status_code == 200
    usd_order = client.post(f"/api/v1/orders/from-negotiation/{started.json()['id']}", headers=as_user(world, "buyer"))
    assert usd_order.status_code == 201, usd_order.text

    spend = client.get(DASHBOARD, headers=as_user(world, "buyer")).json()["spend"]
    assert spend == [
        {"currency": "INR", "amount": kept["totalValue"]["amount"]},
        {"currency": "USD", "amount": "120.00"},
    ]
    assert usd_order.json()["totalValue"]["amount"] == "120.00"


def test_open_negotiations_and_pending_actions(client, world, product):
    started = _start(client, world, product)
    assert started.status_code == 201, started.text
    waiting = client.get(DASHBOARD, headers=as_user(world, "buyer")).json()
    assert waiting["openNegotiations"] == 1
    assert waiting["pendingActions"] == 0
    assert waiting["recentNegotiations"][0]["status"] == "open"
    assert waiting["recentNegotiations"][0]["valueKind"] == "offer"

    countered = _offer(client, world, "supplier", started.json()["id"], "97.50")
    assert countered.status_code == 201, countered.text
    ready = client.get(DASHBOARD, headers=as_user(world, "buyer")).json()
    assert ready["openNegotiations"] == 1
    assert ready["pendingActions"] == 1
    assert ready["recentNegotiations"][0]["status"] == "countered"
    assert ready["recentNegotiations"][0]["value"]["amount"] == "97.5000"
