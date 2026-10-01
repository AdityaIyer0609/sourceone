from sqlalchemy import select

from app.models.identity import Organisation, Role, User, UserRole
from tests.test_api import _flatten, as_actor, as_user
from tests.test_listings import _create
from tests.test_negotiations import product  # noqa: F401

MATCHES = "/api/v1/products"


def _other_supplier(world, name="Second Mill"):
    org = Organisation(code=f"SM-{world.suffix}", name=name, org_type="supplier", dispatch_pin="560001", dispatch_label="Bengaluru")
    world.session.add(org)
    world.session.flush()
    user = User(email=f"mill2-{world.suffix.lower()}@test.local", full_name="Kabir Joshi", organisation_id=org.id)
    world.session.add(user)
    world.session.flush()
    role = world.session.scalar(select(Role).where(Role.code == "supplier"))
    world.session.add(UserRole(user_id=user.id, role_id=role.id))
    world.session.flush()
    return user


def _matches(client, world, product, quantity="1000", pin="382210"):
    return client.get(
        f"{MATCHES}/{product.product_code}/supplier-matches",
        params={"quantity": quantity, "uom": "KG", "destinationPin": pin},
        headers=as_user(world, "buyer"),
    )


def test_match_explains_listing_quantity_and_freight_without_a_score(client, world, product):
    org = world.users["supplier"].organisation
    org.dispatch_pin = "560001"
    org.dispatch_label = "Bengaluru"
    world.session.flush()
    dear = _create(client, world, product, askingPrice="110.0000", minimumQuantity="500").json()
    other = _other_supplier(world)
    cheap = client.post("/api/v1/listings", json={
        "productCode": product.product_code, "minimumQuantity": "500", "askingPrice": "90.0000",
        "currency": "INR", "availability": "limited", "maximumQuantity": "2000",
    }, headers=as_actor(other))
    assert cheap.status_code == 201, cheap.text
    idle = User(email=f"idle-{world.suffix.lower()}@test.local", full_name="No Listing", organisation_id=other.organisation_id)
    world.session.add(idle)
    world.session.flush()
    role = world.session.scalar(select(Role).where(Role.code == "supplier"))
    world.session.add(UserRole(user_id=idle.id, role_id=role.id))
    world.session.flush()

    rule = client.post("/api/v1/admin/freight/rules", json={
        "originPin": "560001", "originLabel": "Bengaluru",
        "destinationPin": "382210", "destinationLabel": "Test yard",
        "ratePerKg": "1.2500", "currency": "INR", "minimumFreight": "1500",
        "isActive": True, "effectiveFrom": "2026-01-01",
    }, headers=as_user(world, "platform"))
    assert rule.status_code == 201, rule.text

    low = _matches(client, world, product, quantity="200")
    assert low.status_code == 200, low.text
    body = low.json()
    assert [row["supplierUserId"] for row in body["matches"]] == [cheap.json()["supplierUserId"], dear["supplierUserId"]]
    assert str(idle.id) not in [row["supplierUserId"] for row in body["matches"]]
    assert body["matches"][0]["meetsMinimum"] is False
    assert any("below the minimum" in reason for reason in body["matches"][0]["reasons"])
    assert body["matches"][0]["freightStatus"] == "estimated"
    assert body["matches"][0]["freight"]["amount"] == "1500.0000"
    keys, _values = _flatten(body)
    assert "score" not in keys and "rank" not in keys and "roadKm" not in keys
    assert all(row["reasons"] for row in body["matches"])
    assert body["matches"][0]["onTimeDelivery"]["available"] is False
    assert body["matches"][0]["quality"]["available"] is False
    assert any("not calculated yet" in reason for reason in body["matches"][0]["reasons"])

    met = _matches(client, world, product, quantity="1000")
    assert met.json()["matches"][0]["meetsMinimum"] is True
    assert any("meets the minimum" in reason for reason in met.json()["matches"][0]["reasons"])

    other_pin = _matches(client, world, product, pin="110001")
    assert other_pin.status_code == 200, other_pin.text
    assert other_pin.json()["matches"][0]["freightStatus"] == "on_request"
    assert other_pin.json()["matches"][0]["freight"] is None
    assert any("on request" in reason for reason in other_pin.json()["matches"][0]["reasons"])
    assert "roadKm" not in _flatten(other_pin.json())[0]
