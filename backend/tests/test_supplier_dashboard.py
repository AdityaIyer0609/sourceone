"""Supplier home counts the same rows the supplier can already list."""

from app.models.listing import SupplierListing
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_negotiations import product  # noqa: F401
from tests.test_orders import _negotiation, _place
from tests.test_purchase_requests import REQUESTS, _body

HOME = "/api/v1/supplier-dashboard"


def test_empty_supplier_home(client, world):
    body = client.get(HOME, headers=as_user(world, "supplier")).json()
    assert body["openRequests"] == 0
    assert body["openNegotiations"] == 0
    assert body["ordersToConfirm"] == 0
    assert body["listingsToReview"] == 0
    assert body["requests"] == [] and body["negotiations"] == [] and body["orders"] == []
    assert body["listings"] == [] and body["documents"] == [] and body["alerts"] == []
    assert body["performance"]["acceptance"]["available"] is False
    assert body["performance"]["onTimeDelivery"]["available"] is False
    assert client.get(HOME, headers=as_user(world, "buyer")).status_code == 403
    assert client.get("/api/v1/dashboard", headers=as_user(world, "supplier")).status_code == 403


def test_queues_match_requests_negotiations_orders_and_listings(client, world, product):
    _create(client, world, product, availability="on_request")
    buyer = as_user(world, "buyer")
    created = client.post(REQUESTS, json=_body(product), headers=buyer).json()
    assert client.put(
        f"{REQUESTS}/{created['id']}/suppliers",
        json={"supplierUserIds": [str(world.users["supplier"].id)]},
        headers=buyer,
    ).status_code == 200
    assert client.post(f"{REQUESTS}/{created['id']}/send", headers=buyer).status_code == 200

    waiting = client.get(HOME, headers=as_user(world, "supplier")).json()
    assert waiting["openRequests"] == len(waiting["requests"]) == 1
    assert waiting["openNegotiations"] == len(waiting["negotiations"]) == 1
    assert waiting["listingsToReview"] == 1
    assert waiting["listings"][0]["availability"] == "on_request"
    assert waiting["alerts"][0]["kind"] == "negotiation"
    assert waiting["ordersToConfirm"] == 0 and waiting["documents"] == []

    listed = client.get("/api/v1/listings", headers=as_user(world, "supplier")).json()
    assert len([row for row in listed if (not row["isActive"]) or row["availability"] == "on_request"]) == waiting["listingsToReview"]

    placed = _place(client, world, _negotiation(world, product))
    assert placed.status_code == 201, placed.text
    confirmed = client.get(HOME, headers=as_user(world, "supplier")).json()
    assert confirmed["ordersToConfirm"] == len(confirmed["orders"]) == 1
    assert confirmed["orders"][0]["id"] == placed.json()["id"]
    assert any(alert["kind"] == "order" for alert in confirmed["alerts"])
    assert client.get(f"/api/v1/orders/{placed.json()['id']}", headers=as_user(world, "alice")).status_code == 403


def test_inactive_listing_is_the_suppliers_own(client, world, product):
    created = _create(client, world, product).json()
    assert client.patch(
        f"/api/v1/listings/{created['id']}", json={"isActive": False}, headers=as_user(world, "supplier"),
    ).status_code == 200
    body = client.get(HOME, headers=as_user(world, "supplier")).json()
    assert body["listingsToReview"] == 1
    assert body["listings"][0]["isActive"] is False
    stored = world.session.get(SupplierListing, created["id"])
    assert stored.supplier_user_id == world.users["supplier"].id
