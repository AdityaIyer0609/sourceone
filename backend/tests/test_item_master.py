from tests.test_api import as_user
from tests.test_negotiations import _start
from tests.test_orders import _negotiation, _place, product  # noqa: F401
from tests.test_products import _publish

ITEMS = "/api/v1/admin/products"


def _body(world, code="A", **extra):
    return {
        "productCode": f"ITEM-{code}-{world.suffix}",
        "name": extra.pop("name", f"Item {code}"),
        "category": extra.pop("category", "Polymers"),
        "subcategory": "Polypropylene",
        "description": "Sellable SourceOne product",
        "uom": "KG",
        "isActive": True,
        **extra,
    }


def test_admin_creates_and_buyer_cannot(client, world):
    created = client.post(ITEMS, json=_body(world), headers=as_user(world, "alice"))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["productCode"] == f"ITEM-A-{world.suffix}"
    assert body["uom"] == "KG" and body["isActive"] is True
    assert body["benchmarkStatus"] == "rate_on_request" and body["listingCount"] == 0
    assert client.post(ITEMS, json=_body(world, code="B"), headers=as_user(world, "buyer")).status_code == 403


def test_edit_and_activate(client, world):
    created = client.post(ITEMS, json=_body(world), headers=as_user(world, "alice")).json()
    edited = client.patch(f"{ITEMS}/{created['productCode']}", json={
        "name": "Renamed raffia", "category": "Resins", "subcategory": "Tape", "description": "Updated",
    }, headers=as_user(world, "alice"))
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Renamed raffia" and edited.json()["category"] == "Resins"
    assert edited.json()["description"] == "Updated" and edited.json()["uom"] == "KG"
    hidden = client.post(f"{ITEMS}/{created['productCode']}/active", json={"isActive": False}, headers=as_user(world, "alice"))
    assert hidden.json()["isActive"] is False
    shown = client.post(f"{ITEMS}/{created['productCode']}/active", json={"isActive": True}, headers=as_user(world, "platform"))
    assert shown.json()["isActive"] is True


def test_search_and_filter(client, world):
    token = world.suffix
    client.post(ITEMS, json=_body(world, code="A", name=f"Zetaquill {token}"), headers=as_user(world, "alice"))
    client.post(ITEMS, json=_body(world, code="B", name="Film liner", category=f"Films-{token}"), headers=as_user(world, "alice"))
    second = client.post(ITEMS, json=_body(world, code="C", name="Inactive film", category=f"Films-{token}", isActive=False), headers=as_user(world, "alice"))
    assert second.status_code == 201
    found = client.get(ITEMS, headers=as_user(world, "alice"), params={"q": f"zetaquill {token}"})
    assert [row["productCode"] for row in found.json()] == [f"ITEM-A-{token}"]
    films = client.get(ITEMS, headers=as_user(world, "alice"), params={"category": f"Films-{token}", "active": True})
    assert [row["name"] for row in films.json()] == ["Film liner"]
    inactive = client.get(ITEMS, headers=as_user(world, "alice"), params={"active": False, "q": token})
    assert [row["productCode"] for row in inactive.json()] == [f"ITEM-C-{token}"]


def test_benchmark_mapping(client, world):
    _publish(world)
    created = client.post(ITEMS, json=_body(world), headers=as_user(world, "alice")).json()
    mapped = client.post(f"{ITEMS}/{created['productCode']}/series", json={
        "seriesCode": world.series["inr"].code, "displayOrder": 10,
    }, headers=as_user(world, "alice"))
    assert mapped.status_code == 201, mapped.text
    body = mapped.json()
    assert body["benchmarkStatus"] == "available"
    assert body["series"][0]["seriesCode"] == world.series["inr"].code
    assert body["series"][0]["availability"] == "available" and body["series"][0]["isActive"] is True
    paused = client.post(
        f"{ITEMS}/{created['productCode']}/series/{world.series['inr'].code}/active",
        json={"isActive": False}, headers=as_user(world, "alice"),
    )
    assert paused.json()["benchmarkStatus"] == "rate_on_request"
    assert paused.json()["series"][0]["isActive"] is False


def test_referenced_product_cannot_be_deleted_and_order_stays(client, world, product):
    placed = _place(client, world, _negotiation(world, product))
    assert placed.status_code == 201, placed.text
    order = placed.json()
    edited = client.patch(f"{ITEMS}/{product.product_code}", json={
        "name": "Renamed after order", "category": product.category, "subcategory": None, "description": product.description,
    }, headers=as_user(world, "alice"))
    assert edited.status_code == 200, edited.text
    refused = client.delete(f"{ITEMS}/{product.product_code}", headers=as_user(world, "alice"))
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PRODUCT_IN_USE"
    current = client.get(f"/api/v1/orders/{order['id']}", headers=as_user(world, "buyer"))
    assert current.status_code == 200
    body = current.json()
    assert body["quantity"] == order["quantity"] and body["status"] == order["status"]
    assert body["agreedPrice"] == order["agreedPrice"] and body["totalValue"] == order["totalValue"]


def test_inactive_product_cannot_start_a_negotiation(client, world, product):
    hidden = client.post(f"{ITEMS}/{product.product_code}/active", json={"isActive": False}, headers=as_user(world, "alice"))
    assert hidden.status_code == 200
    started = _start(client, world, product)
    assert started.status_code == 404
    assert client.get(f"/api/v1/orders", headers=as_user(world, "buyer")).status_code == 200
