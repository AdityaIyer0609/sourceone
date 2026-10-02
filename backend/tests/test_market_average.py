"""The buyer-facing benchmark is the average of active asking prices, not a published admin rate."""

from datetime import timedelta
from decimal import Decimal

from app.catalogue import market_average
from app.core.clock import utcnow
from app.models.listing import SupplierListing
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_negotiations import _start, product  # noqa: F401


def test_product_and_history_follow_the_asking_price_average(client, world, product):
    created = _create(client, world, product, askingPrice="100.0000").json()
    buyer = as_user(world, "buyer")
    detail = client.get(f"/api/v1/products/{product.product_code}", headers=buyer).json()
    assert detail["pricing"][0]["current"]["value"] == {"amount": "100.0000", "currency": "INR"}
    assert detail["pricing"][0]["movement"]["state"] == "insufficient_data"

    listing = world.session.get(SupplierListing, created["id"])
    listing.asking_price = Decimal("110.0000")
    world.session.flush()
    market_average.record(world.session, product.id, "INR", now=utcnow() + timedelta(seconds=1))

    moved = client.get(f"/api/v1/products/{product.product_code}", headers=buyer).json()["pricing"][0]
    assert moved["current"]["value"] == {"amount": "110.0000", "currency": "INR"}
    assert moved["movement"]["percent"] == "10.00"
    history = client.get(
        f"/api/v1/benchmarks/{world.series['inr'].code}/history",
        params={"range": "1Y"},
        headers=buyer,
    ).json()
    assert [point["value"] for point in history["points"]] == ["100.0000", "110.0000"]


def test_negotiation_stores_freight_after_the_supplier_is_chosen(client, world, product):
    listing = _create(client, world, product, askingPrice="100.0000").json()
    started = _start(
        client, world, product, price="99.0000",
        supplierUserId=listing["supplierUserId"], destinationPin="390020", freightBasis="standard",
    )
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["benchmark"]["value"] == {"amount": "100.0000", "currency": "INR"}
    assert body["versions"][0]["offeredPrice"] == {"amount": "99.0000", "currency": "INR"}
    assert body["destinationPin"] == "390020"
    assert body["freightBasis"] == "standard"
    assert body["freightStatus"] in ("estimated", "on_request")
    if body["freightStatus"] == "estimated":
        assert body["freight"]["currency"] == "INR"
        assert body["versions"][0]["offeredPrice"]["amount"] != body["freight"]["amount"]
    assert body["quote"]["offeredPrice"]["amount"] == "99.0000"
    assert body["quote"]["snapshot"]["amount"] == "100.0000"
    assert body["quote"]["currentAverage"]["amount"] == "100.0000"
    assert body["quote"]["versusSnapshot"]["amount"] == "-1.0000"
    assert body["quote"]["versusAverage"]["amount"] == "-1.0000"

    listing_row = world.session.get(SupplierListing, listing["id"])
    listing_row.asking_price = Decimal("110.0000")
    world.session.flush()
    market_average.record(world.session, product.id, "INR", now=utcnow() + timedelta(seconds=1))
    moved = client.get(f"/api/v1/negotiations/{started.json()['id']}", headers=as_user(world, "buyer")).json()
    assert moved["quote"]["snapshot"]["amount"] == "100.0000"
    assert moved["quote"]["currentAverage"]["amount"] == "110.0000"
    assert moved["quote"]["versusSnapshot"]["amount"] == "-1.0000"
    assert moved["quote"]["versusAverage"]["amount"] == "-11.0000"
    assert moved["versions"][0]["offeredPrice"]["amount"] == "99.0000"


def test_spread_needs_two_asks_and_a_withdrawn_listing_adds_no_point(client, world, product):
    from sqlalchemy import func, select

    from app.models.identity import Organisation, Role, User, UserRole
    from app.models.listing import AskingPriceAverage
    from tests.test_api import as_actor

    buyer = as_user(world, "buyer")
    created = _create(client, world, product, askingPrice="100.0000").json()
    one = client.get(f"/api/v1/products/{product.product_code}", headers=buyer).json()["pricing"][0]
    assert one["current"]["value"]["amount"] == "100.0000"
    assert one["spread"]["state"] == "unavailable" and one["spread"]["askCount"] == 1
    before = world.session.scalar(select(func.count()).select_from(AskingPriceAverage).where(AskingPriceAverage.product_id == product.id))
    hidden = client.patch(f"/api/v1/listings/{created['id']}", json={"isActive": False}, headers=as_user(world, "supplier"))
    assert hidden.status_code == 200
    after = world.session.scalar(select(func.count()).select_from(AskingPriceAverage).where(AskingPriceAverage.product_id == product.id))
    assert after == before
    withdrawn = client.get(f"/api/v1/products/{product.product_code}", headers=buyer).json()["pricing"][0]
    assert withdrawn["availability"] == "rate_on_request" and withdrawn["current"] is None
    assert client.patch(f"/api/v1/listings/{created['id']}", json={"isActive": True}, headers=as_user(world, "supplier")).status_code == 200

    other_org = Organisation(code=f"SPR-{world.suffix}", name="Spread Mill", org_type="supplier")
    world.session.add(other_org)
    world.session.flush()
    other = User(email=f"spread-{world.suffix.lower()}@test.local", full_name="Spread Supplier", organisation_id=other_org.id)
    world.session.add(other)
    world.session.flush()
    role = world.session.scalar(select(Role).where(Role.code == "supplier"))
    world.session.add(UserRole(user_id=other.id, role_id=role.id))
    world.session.flush()
    assert client.post("/api/v1/listings", json={
        "productCode": product.product_code, "minimumQuantity": "100", "askingPrice": "80.0000",
        "currency": "INR", "availability": "in_stock", "maximumQuantity": "20000",
    }, headers=as_actor(other)).status_code == 201
    two = client.get(f"/api/v1/products/{product.product_code}", headers=buyer).json()["pricing"][0]
    assert two["current"]["value"]["amount"] == "90.0000"
    assert two["spread"] == {
        "state": "ok", "askCount": 2,
        "minimum": {"amount": "80.0000", "currency": "INR"},
        "maximum": {"amount": "100.0000", "currency": "INR"},
    }
