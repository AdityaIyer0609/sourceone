"""Customers and suppliers do not see other suppliers while the flag is on. Admins still do."""

import pytest

from app.core.config import get_settings
from app.models.listing import SupplierListing
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_negotiations import product  # noqa: F401

ORDERS = "/api/v1/orders"
PIN = "560001"


@pytest.fixture
def hide_suppliers(monkeypatch):
    monkeypatch.setenv("HIDE_SUPPLIERS", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.setenv("HIDE_SUPPLIERS", "false")
    get_settings.cache_clear()


def test_flag_off_still_requires_a_supplier(client, world, product):
    _create(client, world, product)
    response = client.post(
        f"{ORDERS}/for-assignment",
        json={"productCode": product.product_code, "quantity": "500", "destinationPin": PIN},
        headers=as_user(world, "buyer"),
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Choose a supplier when placing this order"


def test_buyer_places_at_the_average_and_admin_assigns(client, world, product, hide_suppliers):
    created = _create(client, world, product, askingPrice="100.0000", maximumQuantity="2000")
    assert created.status_code == 201, created.text
    code = product.product_code
    buyer = as_user(world, "buyer")
    supplier = as_user(world, "supplier")
    admin = as_user(world, "platform")

    matches = client.get(
        f"/api/v1/products/{code}/supplier-matches",
        params={"quantity": "500", "uom": "KG", "destinationPin": PIN},
        headers=buyer,
    )
    assert matches.status_code == 200 and matches.json()["matches"] == []
    assert client.get(
        f"/api/v1/products/{code}/supplier-matches",
        params={"quantity": "500", "uom": "KG", "destinationPin": PIN},
        headers=supplier,
    ).json()["matches"] == []
    assert client.get(f"/api/v1/products/{code}/listings", headers=buyer).json() == []
    own = client.get("/api/v1/listings", headers=supplier)
    assert own.status_code == 200 and len(own.json()) == 1
    admin_matches = client.get(
        f"/api/v1/products/{code}/supplier-matches",
        params={"quantity": "500", "uom": "KG", "destinationPin": PIN},
        headers=admin,
    )
    assert admin_matches.status_code == 200 and len(admin_matches.json()["matches"]) == 1
    assert admin_matches.json()["matches"][0]["organisation"]

    profile = client.get(f"/api/v1/suppliers/{world.users['supplier'].organisation_id}", headers=buyer)
    assert profile.status_code == 403
    assert client.get("/api/v1/negotiations", headers=buyer).json() == []
    assert client.post("/api/v1/purchase-requests", json={
        "productCode": code, "quantity": "500", "uom": "KG", "destinationPin": PIN,
    }, headers=buyer).status_code == 403

    placed = client.post(
        f"{ORDERS}/for-assignment",
        json={"productCode": code, "quantity": "500", "destinationPin": PIN},
        headers=buyer,
    )
    assert placed.status_code == 201, placed.text
    body = placed.json()
    assert body["supplier"] is None and body["negotiation"] is None
    assert body["agreedPrice"]["unitPrice"]["amount"] == "100.0000"
    assert body["status"] == "placed"
    order_id = body["id"]

    waiting = client.get(f"{ORDERS}/unassigned", headers=admin)
    assert waiting.status_code == 200
    assert any(row["id"] == order_id for row in waiting.json())
    assert client.get(f"{ORDERS}/unassigned", headers=buyer).status_code == 403

    assigned = client.post(
        f"{ORDERS}/{order_id}/assign",
        json={"supplierUserId": str(world.users["supplier"].id)},
        headers=admin,
    )
    assert assigned.status_code == 200, assigned.text

    listing = world.session.get(SupplierListing, created.json()["id"])
    assert listing.maximum_quantity == 1500

    hidden = client.get(f"{ORDERS}/{order_id}", headers=buyer)
    assert hidden.status_code == 200
    assert hidden.json()["supplier"] is None and hidden.json()["negotiation"] is None

    visible = client.get(ORDERS, headers=supplier)
    assert visible.status_code == 200
    [row] = [item for item in visible.json() if item["id"] == order_id]
    assert row["buyer"]["name"] == world.users["buyer"].full_name
    assert row["supplier"]["name"] == world.users["supplier"].full_name
    assert row["negotiation"] is None
