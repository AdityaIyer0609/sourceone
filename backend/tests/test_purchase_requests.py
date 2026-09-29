"""Purchase requests open negotiations. They do not create orders."""

from sqlalchemy import func, select

from app.catalogue import products as catalogue
from app.models.order import Order
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_negotiations import product  # noqa: F401

REQUESTS = "/api/v1/purchase-requests"
NEGOTIATIONS = "/api/v1/negotiations"
ORDERS = "/api/v1/orders"


def _body(product, **extra):
    return {
        "productCode": product.product_code, "quantity": "1000", "uom": "KG",
        "destinationPin": "560001", "message": "Need this week", **extra,
    }


def test_buyer_creates_a_numbered_draft_and_hides_it_from_the_supplier(client, world, product):
    created = client.post(REQUESTS, json=_body(product), headers=as_user(world, "buyer"))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["requestNumber"].startswith("RFQ-")
    assert body["status"] == "draft" and body["suppliers"] == []
    assert body["uom"] == "KG" and body["productCode"] == product.product_code
    assert body["canSend"] is False
    listed = client.get(REQUESTS, headers=as_user(world, "buyer")).json()
    assert body["id"] in {row["id"] for row in listed}
    supplier_ids = {row["id"] for row in client.get(REQUESTS, headers=as_user(world, "supplier")).json()}
    assert body["id"] not in supplier_ids
    assert client.post(REQUESTS, json=_body(product, uom="MT"), headers=as_user(world, "buyer")).status_code == 422
    hidden = catalogue.create_product(
        world.session, product_code=f"OFF-{world.suffix}", name="Inactive", category="Hidden", uom="KG", is_active=False,
    )
    assert client.post(REQUESTS, json=_body(hidden), headers=as_user(world, "buyer")).status_code == 404


def test_send_opens_a_negotiation_and_does_not_create_an_order(client, world, product):
    _create(client, world, product)
    buyer = as_user(world, "buyer")
    orders_before = world.session.scalar(select(func.count()).select_from(Order))
    created = client.post(REQUESTS, json=_body(product), headers=buyer).json()
    empty = client.post(f"{REQUESTS}/{created['id']}/send", headers=buyer)
    assert empty.status_code == 422
    assigned = client.put(
        f"{REQUESTS}/{created['id']}/suppliers",
        json={"supplierUserIds": [str(world.users["supplier"].id)]},
        headers=buyer,
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["suppliers"][0]["freightStatus"] == "on_request"
    assert assigned.json()["suppliers"][0]["askingPrice"]["amount"] == "100.2500"
    sent = client.post(f"{REQUESTS}/{created['id']}/send", headers=buyer)
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "sent"
    supplier_row = body["suppliers"][0]
    assert supplier_row["negotiationNumber"].startswith("NEG-")
    assert supplier_row["negotiationStatus"] == "open"
    assert world.session.scalar(select(func.count()).select_from(Order)) == orders_before
    visible = client.get(REQUESTS, headers=as_user(world, "supplier")).json()
    assert created["id"] in {row["id"] for row in visible}
    assert visible[0]["viewerRole"] == "supplier" or any(row["id"] == created["id"] and row["viewerRole"] == "supplier" for row in visible)
    countered = client.post(
        f"{NEGOTIATIONS}/{supplier_row['negotiationId']}/offers",
        json={"offeredPrice": "99.50"},
        headers=as_user(world, "supplier"),
    )
    assert countered.status_code == 201, countered.text
    refreshed = client.get(f"{REQUESTS}/{created['id']}", headers=buyer).json()
    assert refreshed["status"] == "in_negotiation"
    accepted = client.post(f"{NEGOTIATIONS}/{supplier_row['negotiationId']}/accept", headers=buyer)
    assert accepted.status_code == 200, accepted.text
    order = client.post(f"{ORDERS}/from-negotiation/{supplier_row['negotiationId']}", headers=buyer)
    assert order.status_code == 201, order.text
    converted = client.get(f"{REQUESTS}/{created['id']}", headers=buyer).json()
    assert converted["status"] == "converted"
    assert converted["canCancel"] is False


def test_ineligible_supplier_is_rejected_and_a_draft_can_be_cancelled(client, world, product):
    buyer = as_user(world, "buyer")
    created = client.post(REQUESTS, json=_body(product), headers=buyer).json()
    refused = client.put(
        f"{REQUESTS}/{created['id']}/suppliers",
        json={"supplierUserIds": [str(world.users["supplier"].id)]},
        headers=buyer,
    )
    assert refused.status_code == 422
    cancelled = client.post(f"{REQUESTS}/{created['id']}/cancel", headers=buyer)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.post(f"{REQUESTS}/{created['id']}/send", headers=buyer).status_code == 409
