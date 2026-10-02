from decimal import Decimal

from sqlalchemy import func, select

from app.models.listing import AskingPriceAverage, SupplierListing
from app.models.pricing import BenchmarkRate
from tests.test_api import as_user
from tests.test_negotiations import _start, product  # noqa: F401

LISTINGS = "/api/v1/listings"


def _create(client, world, product, key="supplier", **extra):
    body = {
        "productCode": product.product_code, "minimumQuantity": "500", "askingPrice": "100.2500",
        "currency": "INR", "availability": "in_stock", "isActive": True, **extra,
    }
    if body["availability"] == "in_stock" and "maximumQuantity" not in body:
        body["maximumQuantity"] = "20000"
    return client.post(LISTINGS, json=body, headers=as_user(world, key))


def test_supplier_creates_a_listing(client, world, product):
    response = _create(client, world, product)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["productCode"] == product.product_code
    assert body["supplierUserId"] == str(world.users["supplier"].id)
    assert body["uom"] == "KG" and body["minimumQuantity"] == "500"
    assert body["askingPrice"] == {"amount": "100.2500", "currency": "INR"}
    assert body["availability"] == "in_stock" and body["isActive"] is True
    assert body["maximumQuantity"] == "20000"
    assert client.post(LISTINGS, json={
        "productCode": product.product_code, "minimumQuantity": "1", "askingPrice": "1",
        "currency": "INR", "availability": "in_stock",
    }, headers=as_user(world, "buyer")).status_code == 403


def test_inactive_listing_and_inactive_supplier_are_hidden(client, world, product):
    created = _create(client, world, product).json()
    hidden = client.patch(f"{LISTINGS}/{created['id']}", json={"isActive": False}, headers=as_user(world, "supplier"))
    assert hidden.status_code == 200 and hidden.json()["isActive"] is False
    assert client.get(f"/api/v1/products/{product.product_code}/listings", headers=as_user(world, "buyer")).json() == []

    shown = client.patch(f"{LISTINGS}/{created['id']}", json={"isActive": True}, headers=as_user(world, "supplier"))
    assert shown.json()["isActive"] is True
    world.users["supplier"].is_active = False
    world.session.flush()
    assert client.get(f"/api/v1/products/{product.product_code}/listings", headers=as_user(world, "buyer")).json() == []


def test_buyer_sees_only_eligible_listings_for_the_product(client, world, product):
    _create(client, world, product, askingPrice="101.0000", availability="limited", maximumQuantity="2000")
    other_listing = _create(client, world, product, key="supplier", minimumQuantity="250")
    assert other_listing.status_code == 422
    visible = client.get(
        f"/api/v1/products/{product.product_code}/listings", headers=as_user(world, "buyer"), params={"currency": "INR"},
    )
    assert visible.status_code == 200, visible.text
    [row] = visible.json()
    assert row["organisation"] == world.users["supplier"].organisation.name
    assert row["askingPrice"]["amount"] == "101.0000"
    assert row["supplierUserId"] != str(world.users["buyer"].id)
    usd = client.get(
        f"/api/v1/products/{product.product_code}/listings", headers=as_user(world, "buyer"), params={"currency": "USD"},
    )
    assert usd.json() == []


def test_negotiation_uses_the_selected_supplier_and_benchmark_stays_separate(client, world, product):
    before = world.session.scalar(select(func.count()).select_from(BenchmarkRate))
    listing = _create(client, world, product, askingPrice="100.2500").json()
    assert world.session.scalar(select(func.count()).select_from(BenchmarkRate)) == before
    started = _start(client, world, product, price="100.2500", supplierUserId=listing["supplierUserId"])
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["supplier"]["name"] == world.users["supplier"].full_name
    assert body["benchmark"]["value"] == {"amount": "100.2500", "currency": "INR"}
    assert body["benchmark"]["basis"] == "ASKING_AVERAGE/GST_EXCLUDED"
    assert body["versions"][0]["offeredPrice"] == {"amount": "100.2500", "currency": "INR"}
    assert world.session.get(SupplierListing, listing["id"]).asking_price == Decimal("100.2500")
    assert world.session.scalar(select(func.count()).select_from(BenchmarkRate)) == before


def test_price_edit_updates_the_listing_and_the_average_not_a_benchmark(client, world, product):
    created = _create(client, world, product, askingPrice="100.0000").json()
    averages = select(func.count()).select_from(AskingPriceAverage).where(AskingPriceAverage.product_id == product.id)
    before_average = world.session.scalar(averages)
    before_benchmark = world.session.scalar(select(func.count()).select_from(BenchmarkRate))
    same = client.patch(f"{LISTINGS}/{created['id']}", json={"askingPrice": "100.0000"}, headers=as_user(world, "supplier"))
    assert same.status_code == 200, same.text
    assert world.session.scalar(averages) == before_average
    changed = client.patch(f"{LISTINGS}/{created['id']}", json={"askingPrice": "110.0000"}, headers=as_user(world, "supplier"))
    assert changed.status_code == 200, changed.text
    assert changed.json()["askingPrice"]["amount"] == "110.0000"
    assert world.session.scalar(averages) == before_average + 1
    assert world.session.scalar(select(func.count()).select_from(BenchmarkRate)) == before_benchmark
    own = client.get(LISTINGS, headers=as_user(world, "supplier")).json()
    assert created["id"] in {row["id"] for row in own}
    assert client.get(LISTINGS, headers=as_user(world, "buyer")).status_code == 403


def test_selling_listings_carry_stock_and_on_request_does_not(client, world, product):
    missing = _create(client, world, product, availability="limited")
    assert missing.status_code == 422
    created = _create(client, world, product, availability="limited", maximumQuantity="800")
    assert created.status_code == 201, created.text
    assert created.json()["maximumQuantity"] == "800"
    stock = client.patch(
        f"{LISTINGS}/{created.json()['id']}",
        json={"availability": "in_stock", "maximumQuantity": "800"},
        headers=as_user(world, "supplier"),
    )
    assert stock.status_code == 200, stock.text
    assert stock.json()["maximumQuantity"] == "800"
    cleared = client.patch(
        f"{LISTINGS}/{created.json()['id']}",
        json={"availability": "in_stock", "maximumQuantity": None},
        headers=as_user(world, "supplier"),
    )
    assert cleared.status_code == 422
    limited = client.patch(
        f"{LISTINGS}/{created.json()['id']}",
        json={"availability": "limited", "maximumQuantity": "800"},
        headers=as_user(world, "supplier"),
    )
    assert limited.status_code == 200, limited.text
    matches = client.get(
        f"/api/v1/products/{product.product_code}/supplier-matches",
        headers=as_user(world, "buyer"),
        params={"quantity": "900", "uom": "KG", "destinationPin": "560001"},
    )
    assert matches.status_code == 200, matches.text
    [row] = matches.json()["matches"]
    assert row["meetsMinimum"] is True
    assert row["maximumQuantity"] == "800"
    assert any("can spare" in reason for reason in row["reasons"])


def test_direct_order_uses_the_asking_price_and_reduces_stock(client, world, product):
    created = _create(client, world, product, maximumQuantity="1000").json()
    placed = client.post("/api/v1/orders/from-listing", json={
        "productCode": product.product_code,
        "supplierUserId": str(world.users["supplier"].id),
        "quantity": "600",
        "destinationPin": "560001",
    }, headers=as_user(world, "buyer"))
    assert placed.status_code == 201, placed.text
    body = placed.json()
    assert body["agreedPrice"]["unitPrice"]["amount"] == "100.2500"
    assert body["quantity"] == "600"
    listing = client.get("/api/v1/listings", headers=as_user(world, "supplier")).json()
    row = next(item for item in listing if item["id"] == created["id"])
    assert row["maximumQuantity"] == "400"
    again = client.post("/api/v1/orders/from-listing", json={
        "productCode": product.product_code,
        "supplierUserId": str(world.users["supplier"].id),
        "quantity": "500",
        "destinationPin": "560001",
    }, headers=as_user(world, "buyer"))
    assert again.status_code == 201, again.text
    assert again.json()["quantity"] == "400"
    sold = client.get("/api/v1/listings", headers=as_user(world, "supplier")).json()
    emptied = next(item for item in sold if item["id"] == created["id"])
    assert emptied["maximumQuantity"] is None and emptied["availability"] == "on_request"
    blocked = client.post("/api/v1/orders/from-listing", json={
        "productCode": product.product_code,
        "supplierUserId": str(world.users["supplier"].id),
        "quantity": "100",
        "destinationPin": "560001",
    }, headers=as_user(world, "buyer"))
    assert blocked.status_code == 422
