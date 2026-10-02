from sqlalchemy import select

from app.models.identity import Organisation, Role, User, UserRole
from tests.test_api import _flatten, as_actor, as_user
from tests.test_negotiations import _other_buyer, _start, product  # noqa: F401

PROFILE = "/api/v1/suppliers"


def _supplier_org(world, *, name="Harbour Mills"):
    org = Organisation(
        code=f"SUP-{world.suffix}", name=name, org_type="supplier",
        dispatch_pin="380015", dispatch_label="Ahmedabad yard",
    )
    world.session.add(org)
    world.session.flush()
    user = User(
        email=f"mill-{world.suffix.lower()}@test.local", full_name="Meera Shah", organisation_id=org.id,
    )
    world.session.add(user)
    world.session.flush()
    role = world.session.scalar(select(Role).where(Role.code == "supplier"))
    world.session.add(UserRole(user_id=user.id, role_id=role.id))
    world.session.flush()
    return org, user


def test_new_supplier_has_no_invented_rates(client, world, product):
    org, user = _supplier_org(world)
    created = client.post("/api/v1/listings", json={
        "productCode": product.product_code, "minimumQuantity": "500", "askingPrice": "100.2500",
        "currency": "INR", "availability": "in_stock", "maximumQuantity": "20000",
    }, headers=as_actor(user))
    assert created.status_code == 201, created.text

    profile = client.get(f"{PROFILE}/{org.id}", headers=as_user(world, "buyer"))
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["name"] == "Harbour Mills"
    assert body["verificationStatus"] == "unverified"
    assert body["dispatchPin"] == "380015" and body["dispatchLabel"] == "Ahmedabad yard"
    assert body["products"][0]["productCode"] == product.product_code
    assert body["products"][0]["askingPrice"] == {"amount": "100.2500", "currency": "INR"}
    assert body["responseTime"] == {
        "available": False, "note": "No supplier reply has followed a buyer offer yet.",
        "sampleCount": 0, "averageHours": None,
    }
    assert body["acceptance"]["available"] is False and body["acceptance"]["percent"] is None
    assert body["orderCancellation"]["available"] is False and body["orderCancellation"]["percent"] is None
    assert body["onTimeDelivery"]["available"] is False and body["onTimeDelivery"]["percent"] is None
    assert body["quality"]["available"] is False and body["quality"]["percent"] is None
    assert body["quoteCount"] == 0 and body["orderCount"] == 0
    assert body["people"] == [{"name": "Meera Shah", "email": None}]
    keys, values = _flatten(body)
    assert not [key for key in keys if any(word in key.lower() for word in ("gstin", "pan", "erp"))]
    assert "380015" in values

    assert client.get(f"{PROFILE}/{org.id}", headers=as_user(world, "supplier")).status_code == 403
    assert client.get(f"{PROFILE}/{org.id}", headers=as_user(world, "alice")).status_code == 403
    own = client.get(f"{PROFILE}/{org.id}", headers=as_actor(user))
    assert own.status_code == 200 and own.json()["people"][0]["email"] == user.email


def test_rates_use_real_negotiations_and_orders(client, world, product):
    org, user = _supplier_org(world, name="Kutch Resin")
    assert client.post("/api/v1/listings", json={
        "productCode": product.product_code, "minimumQuantity": "100", "askingPrice": "101.0000",
        "currency": "INR", "availability": "limited", "maximumQuantity": "20000",
    }, headers=as_actor(user)).status_code == 201
    started = _start(client, world, product, price="101.0000", supplierUserId=str(user.id))
    assert started.status_code == 201, started.text
    negotiation_id = started.json()["id"]
    countered = client.post(
        f"/api/v1/negotiations/{negotiation_id}/offers",
        json={"offeredPrice": "100.5000"}, headers=as_actor(user),
    )
    assert countered.status_code == 201, countered.text

    open_profile = client.get(f"{PROFILE}/{org.id}", headers=as_user(world, "buyer")).json()
    assert open_profile["responseTime"]["available"] is True
    assert open_profile["responseTime"]["sampleCount"] == 1
    assert open_profile["responseTime"]["averageHours"] is not None
    assert open_profile["acceptance"]["available"] is False
    assert open_profile["quoteCount"] == 1
    assert open_profile["quotes"][0]["reference"] == started.json()["negotiationNumber"]
    assert open_profile["quotes"][0]["latestOffer"]["amount"] == "100.5000"

    accepted = client.post(f"/api/v1/negotiations/{negotiation_id}/accept", headers=as_user(world, "buyer"))
    assert accepted.status_code == 200, accepted.text
    order = client.post(
        f"/api/v1/orders/from-negotiation/{negotiation_id}",
        json={"destinationPin": "382415", "freightBasis": "standard"},
        headers=as_user(world, "buyer"),
    )
    assert order.status_code == 201, order.text
    cancelled = client.post(
        f"/api/v1/orders/{order.json()['id']}/cancel",
        json={"reason": "Buyer withdrew"}, headers=as_user(world, "buyer"),
    )
    assert cancelled.status_code == 200, cancelled.text

    body = client.get(f"{PROFILE}/{org.id}", headers=as_user(world, "buyer")).json()
    assert body["acceptance"] == {
        "available": True,
        "note": "Accepted negotiations divided by negotiations that were accepted, rejected, or cancelled.",
        "count": 1, "total": 1, "percent": "100.00",
    }
    assert body["orderCancellation"]["available"] is True
    assert body["orderCancellation"]["count"] == 1 and body["orderCancellation"]["total"] == 1
    assert body["orderCancellation"]["percent"] == "100.00"
    assert body["onTimeDelivery"]["percent"] is None
    assert body["orderCount"] == 1 and body["orders"][0]["status"] == "cancelled"

    outsider = client.get(f"{PROFILE}/{org.id}", headers=as_actor(_other_buyer(world))).json()
    assert outsider["quoteCount"] == 1 and outsider["orderCount"] == 1
    assert outsider["quotes"] == [] and outsider["orders"] == []
    assert outsider["acceptance"]["percent"] == "100.00"
    own = client.get(f"{PROFILE}/{org.id}", headers=as_actor(user)).json()
    assert own["quotes"][0]["reference"] == started.json()["negotiationNumber"]
    assert own["orders"][0]["status"] == "cancelled"


def test_supplier_declares_regions_and_admin_sets_verification(client, world, product):
    org, user = _supplier_org(world)
    buyer = as_user(world, "buyer")
    denied = client.put(
        f"{PROFILE}/{org.id}/service-regions",
        json={"regions": [{"label": "Gujarat", "pinPrefix": "380"}]}, headers=buyer,
    )
    assert denied.status_code == 403
    saved = client.put(
        f"{PROFILE}/{org.id}/service-regions",
        json={"regions": [{"label": "Gujarat", "pinPrefix": "380"}, {"label": "Saurashtra", "pinPrefix": "360"}]},
        headers=as_actor(user),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["serviceRegions"] == [
        {"label": "Gujarat", "pinPrefix": "380"},
        {"label": "Saurashtra", "pinPrefix": "360"},
    ]
    assert saved.json()["dispatchPin"] == "380015"
    bad = client.put(
        f"{PROFILE}/{org.id}/service-regions",
        json={"regions": [{"label": "Too short", "pinPrefix": "38"}]}, headers=as_actor(user),
    )
    assert bad.status_code == 422

    assert client.patch(
        f"{PROFILE}/{org.id}/verification", json={"status": "verified"}, headers=as_actor(user),
    ).status_code == 403
    verified = client.patch(
        f"{PROFILE}/{org.id}/verification", json={"status": "verified"}, headers=as_user(world, "platform"),
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verificationStatus"] == "verified"
    assert client.get(f"{PROFILE}/{world.users['buyer'].organisation_id}", headers=buyer).status_code == 404
