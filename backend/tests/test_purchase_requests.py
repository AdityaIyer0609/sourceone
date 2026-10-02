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
    order = client.post(
        f"{ORDERS}/from-negotiation/{supplier_row['negotiationId']}",
        json={"destinationPin": "560076"},
        headers=buyer,
    )
    assert order.status_code == 201, order.text
    converted = client.get(f"{REQUESTS}/{created['id']}", headers=buyer).json()
    assert converted["status"] == "converted"
    assert converted["canCancel"] is False


def test_comparison_keeps_each_suppliers_offer_and_snapshots_the_request(client, world, product):
    from sqlalchemy import select

    from app.models.identity import Organisation, Role, User, UserRole

    org = world.users["supplier"].organisation
    org.dispatch_pin = "560001"
    org.dispatch_label = "Bengaluru"
    world.session.flush()
    _create(client, world, product, askingPrice="100.2500")
    other_org = Organisation(code=f"RFQ-{world.suffix}", name="Second Mill", org_type="supplier", dispatch_pin="560001", dispatch_label="Bengaluru")
    world.session.add(other_org)
    world.session.flush()
    other = User(email=f"rfq-{world.suffix.lower()}@test.local", full_name="Second Supplier", organisation_id=other_org.id)
    world.session.add(other)
    world.session.flush()
    role = world.session.scalar(select(Role).where(Role.code == "supplier"))
    world.session.add(UserRole(user_id=other.id, role_id=role.id))
    world.session.flush()
    from tests.test_api import as_actor
    assert client.post("/api/v1/listings", json={
        "productCode": product.product_code, "minimumQuantity": "100", "askingPrice": "90.0000",
        "currency": "INR", "availability": "in_stock", "maximumQuantity": "20000",
    }, headers=as_actor(other)).status_code == 201
    assert client.post("/api/v1/admin/freight/rules", json={
        "originPin": "560001", "originLabel": "Bengaluru", "destinationPin": "560001",
        "destinationLabel": "Same city", "ratePerKg": "1.2500", "currency": "INR", "minimumFreight": "1500",
        "isActive": True, "effectiveFrom": "2026-01-01",
    }, headers=as_user(world, "platform")).status_code == 201

    buyer = as_user(world, "buyer")
    created = client.post(REQUESTS, json=_body(
        product, requiredBy="2026-10-15", paymentTerms="30 days",
        supplierUserIds=[str(world.users["supplier"].id), str(other.id)],
    ), headers=buyer)
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["requiredBy"] == "2026-10-15" and draft["paymentTerms"] == "30 days"
    assert isinstance(draft["requirements"], list)
    sent = client.post(f"{REQUESTS}/{draft['id']}/send", headers=buyer)
    assert sent.status_code == 200, sent.text
    rows = {row["supplierUserId"]: row for row in sent.json()["suppliers"]}
    assert set(rows) == {str(world.users["supplier"].id), str(other.id)}
    for row in rows.values():
        assert row["negotiationStatus"] == "open"
        assert row["freightStatus"] == "estimated"
        assert row["freight"]["amount"] == "1500.0000"
        room = client.get(f"{NEGOTIATIONS}/{row['negotiationId']}", headers=buyer).json()
        assert room["destinationPin"] == "560001"
        assert room["requiredBy"] == "2026-10-15" and room["paymentTerms"] == "30 days"
        assert room["deliveryNote"] == "Delivery date has not been offered"
        assert len(room["versions"]) == 1
    first = rows[str(world.users["supplier"].id)]
    second = rows[str(other.id)]
    assert client.post(f"{NEGOTIATIONS}/{first['negotiationId']}/offers", json={"offeredPrice": "99.5000", "deliveryDate": "2026-10-15"}, headers=as_user(world, "supplier")).status_code == 201
    assert client.post(f"{NEGOTIATIONS}/{second['negotiationId']}/offers", json={"offeredPrice": "88.0000", "deliveryDate": "2026-10-15"}, headers=as_actor(other)).status_code == 201
    compared = {row["supplierUserId"]: row for row in client.get(f"{REQUESTS}/{draft['id']}", headers=buyer).json()["suppliers"]}
    assert compared[str(world.users["supplier"].id)]["latestOffer"]["amount"] == "99.5000"
    assert compared[str(other.id)]["latestOffer"]["amount"] == "88.0000"
    assert compared[str(world.users["supplier"].id)]["askingPrice"]["amount"] == "100.2500"
    assert compared[str(world.users["supplier"].id)]["materialValue"]["amount"] == "99500.0000"
    assert compared[str(world.users["supplier"].id)]["landedEstimate"]["amount"] == "101000.0000"
    charges = compared[str(world.users["supplier"].id)]["charges"]
    assert charges["gstRatePercent"] == 18
    assert charges["gstBasis"] == "GST extra at 18% on material and estimated freight"
    assert charges["gst"]["amount"] == "18180.0000"
    assert charges["payable"]["amount"] == "119180.0000"
    assert charges["payable"]["amount"] != compared[str(world.users["supplier"].id)]["latestOffer"]["amount"]
    quote = compared[str(world.users["supplier"].id)]["quote"]
    assert quote["offeredPrice"]["amount"] == "99.5000"
    assert quote["snapshot"]["amount"] == "95.1250"
    assert quote["currentAverage"]["amount"] == "95.1250"
    assert quote["versusSnapshot"]["amount"] == "4.3750"
    assert quote["versusAverage"]["amount"] == "4.3750"
    room = client.get(f"{NEGOTIATIONS}/{first['negotiationId']}", headers=buyer).json()
    assert len(room["versions"]) == 2
    assert room["deliveryNote"] == "On the requested date"
    assert room["versions"][1]["deliveryDate"] == "2026-10-15"
    assert room["versions"][0]["deliveryDate"] is None
    omitted = client.post(REQUESTS, json=_body(product), headers=buyer).json()
    assert omitted["requiredBy"] is None


def test_supplier_delivery_date_is_measured_against_the_fixed_request(client, world, product):
    _create(client, world, product)
    buyer = as_user(world, "buyer")
    supplier = as_user(world, "supplier")
    created = client.post(
        REQUESTS,
        json=_body(product, requiredBy="2026-10-15", supplierUserIds=[str(world.users["supplier"].id)]),
        headers=buyer,
    )
    assert created.status_code == 201, created.text
    sent = client.post(f"{REQUESTS}/{created.json()['id']}/send", headers=buyer)
    assert sent.status_code == 200, sent.text
    negotiation_id = sent.json()["suppliers"][0]["negotiationId"]
    missing = client.post(f"{NEGOTIATIONS}/{negotiation_id}/offers", json={"offeredPrice": "99"}, headers=supplier)
    assert missing.status_code == 422
    early = client.post(
        f"{NEGOTIATIONS}/{negotiation_id}/offers",
        json={"offeredPrice": "99", "deliveryDate": "2026-10-11"},
        headers=supplier,
    )
    assert early.status_code == 201, early.text
    assert early.json()["requiredBy"] == "2026-10-15"
    assert early.json()["deliveryNote"] == "4 days before the requested date"
    blocked = client.post(
        f"{NEGOTIATIONS}/{negotiation_id}/offers",
        json={"offeredPrice": "98", "deliveryDate": "2026-10-01"},
        headers=buyer,
    )
    assert blocked.status_code == 422
    kept = client.post(f"{NEGOTIATIONS}/{negotiation_id}/offers", json={"offeredPrice": "98"}, headers=buyer)
    assert kept.status_code == 201, kept.text
    assert kept.json()["deliveryNote"] == "4 days before the requested date"
    assert kept.json()["versions"][-1]["deliveryDate"] is None
    later = client.post(
        f"{NEGOTIATIONS}/{negotiation_id}/offers",
        json={"offeredPrice": "99.25", "deliveryDate": "2026-10-19"},
        headers=supplier,
    )
    assert later.status_code == 201, later.text
    assert later.json()["deliveryNote"] == "4 days after the requested date"
    assert later.json()["versions"][-1]["deliveryDate"] == "2026-10-19"
    assert client.post(f"{NEGOTIATIONS}/{negotiation_id}/offers", json={"offeredPrice": "97.90"}, headers=buyer).status_code == 201
    unchanged = client.post(f"{NEGOTIATIONS}/{negotiation_id}/offers", json={"offeredPrice": "99.10"}, headers=supplier)
    assert unchanged.status_code == 201, unchanged.text
    assert unchanged.json()["deliveryNote"] == "4 days after the requested date"
    assert unchanged.json()["versions"][-1]["deliveryDate"] == "2026-10-19"


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


def test_buyer_price_is_the_opening_offer(client, world, product):
    _create(client, world, product)
    buyer = as_user(world, "buyer")
    created = client.post(REQUESTS, json=_body(
        product, offeredPrice="97.5000", supplierUserIds=[str(world.users["supplier"].id)],
    ), headers=buyer)
    assert created.status_code == 201, created.text
    assert created.json()["offeredPrice"] == "97.5000"
    sent = client.post(f"{REQUESTS}/{created.json()['id']}/send", headers=buyer)
    assert sent.status_code == 200, sent.text
    room = client.get(f"{NEGOTIATIONS}/{sent.json()['suppliers'][0]['negotiationId']}", headers=buyer)
    assert room.status_code == 200, room.text
    assert room.json()["versions"][0]["offeredPrice"]["amount"] == "97.5000"


def test_cancelling_one_supplier_leaves_the_request_open(client, world, product):
    from sqlalchemy import select

    from app.models.identity import Organisation, Role, User, UserRole
    from tests.test_api import as_actor

    _create(client, world, product)
    other_org = Organisation(code=f"ONE-{world.suffix}", name="One Mill", org_type="supplier")
    world.session.add(other_org)
    world.session.flush()
    other = User(email=f"one-{world.suffix.lower()}@test.local", full_name="One Supplier", organisation_id=other_org.id)
    world.session.add(other)
    world.session.flush()
    role = world.session.scalar(select(Role).where(Role.code == "supplier"))
    world.session.add(UserRole(user_id=other.id, role_id=role.id))
    world.session.flush()
    assert client.post("/api/v1/listings", json={
        "productCode": product.product_code, "minimumQuantity": "100", "askingPrice": "90.0000",
        "currency": "INR", "availability": "in_stock", "maximumQuantity": "20000",
    }, headers=as_actor(other)).status_code == 201
    buyer = as_user(world, "buyer")
    created = client.post(REQUESTS, json=_body(
        product, supplierUserIds=[str(world.users["supplier"].id), str(other.id)],
    ), headers=buyer)
    assert created.status_code == 201, created.text
    sent = client.post(f"{REQUESTS}/{created.json()['id']}/send", headers=buyer)
    assert sent.status_code == 200, sent.text
    cancelled = client.post(
        f"{REQUESTS}/{created.json()['id']}/suppliers/{world.users['supplier'].id}/cancel",
        headers=buyer,
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "sent"
    rows = {row["supplierUserId"]: row["negotiationStatus"] for row in body["suppliers"]}
    assert rows[str(world.users["supplier"].id)] == "cancelled"
    assert rows[str(other.id)] == "open"
