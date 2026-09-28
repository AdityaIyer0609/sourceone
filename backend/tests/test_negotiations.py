import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.catalogue import products as catalogue
from app.core.clock import business_today, utcnow
from app.core.errors import AwaitingCounterparty, InvalidStateTransition, NegotiationClosed, NotFound
from app.models.identity import Organisation, Role, User, UserRole
from app.models.negotiation import Negotiation
from app.negotiation import service
from app.pricing import service as pricing_service
from tests.test_api import _flatten, as_user

NEGOTIATIONS = "/api/v1/negotiations"


def _publish(world, value, days_ago=1, series="inr"):
    as_of = business_today(utcnow()) - timedelta(days=days_ago)
    draft = world.manual("alice", series, value, as_of=as_of)
    pricing_service.submit_benchmark(world.session, world.actors["alice"], draft.id)
    return pricing_service.publish_benchmark(world.session, world.actors["bob"], draft.id)


@pytest.fixture
def product(world):
    _publish(world, "99.40")
    item = catalogue.create_product(world.session, product_code=f"NEG-{world.suffix}", name="Negotiable PP",
                                    category=f"cat-{world.suffix}", uom="KG")
    catalogue.map_rate_series(world.session, item, world.series["inr"])
    return item


def _start(client, world, product, price="98.00", **extra):
    body = {"productCode": product.product_code, "quantity": "12000", "offeredPrice": price,
            "message": "First offer", "supplierUserId": str(world.users["supplier"].id), **extra}
    return client.post(NEGOTIATIONS, json=body, headers=as_user(world, "buyer"))


def _offer(client, world, key, negotiation_id, price, **extra):
    return client.post(f"{NEGOTIATIONS}/{negotiation_id}/offers", json={"offeredPrice": price, **extra},
                       headers=as_user(world, key))


def _other_buyer(world):
    org = world.session.get(Organisation, world.users["buyer"].organisation_id)
    user = User(email=f"buyer2-{world.suffix.lower()}@test.local", full_name="Other buyer", organisation_id=org.id)
    world.session.add(user)
    world.session.flush()
    role = world.session.scalar(select(Role).where(Role.code == "buyer"))
    world.session.add(UserRole(user_id=user.id, role_id=role.id))
    world.session.flush()
    return user


def test_create_negotiation_snapshots_benchmark(client, world, product):
    response = _start(client, world, product)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "open" and body["negotiationNumber"].startswith("NEG-")
    assert body["benchmark"] == {
        "priceKind": "sourceone_benchmark", "label": "SourceOne benchmark (reference at start)", "state": "fresh",
        "value": {"amount": "99.4000", "currency": "INR"},
        "asOfDate": (business_today(utcnow()) - timedelta(days=1)).isoformat(),
        "seriesCode": world.series["inr"].code, "basis": "DELIVERED/GST_EXCLUDED",
    }
    [v1] = body["versions"]
    assert v1["versionNumber"] == 1 and v1["offeredBy"] == "buyer" and v1["priceKind"] == "offer"
    assert v1["offeredPrice"] == {"amount": "98.0000", "currency": "INR"} and v1["quantity"] == "12000"
    assert body["negotiated"] is None and body["awaiting"] == "supplier" and body["viewerRole"] == "buyer"
    assert body["allowedActions"] == {"offer": False, "accept": False, "reject": False, "cancel": True}


def test_draft_without_offer_then_first_offer_opens(client, world, product):
    draft = _start(client, world, product, offeredPrice=None).json()
    assert draft["status"] == "draft" and draft["versions"] == []
    assert client.get(f"{NEGOTIATIONS}/{draft['id']}", headers=as_user(world, "supplier")).status_code == 404
    accept = client.post(f"{NEGOTIATIONS}/{draft['id']}/accept", headers=as_user(world, "buyer"))
    assert accept.status_code == 409 and accept.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    opened = _offer(client, world, "buyer", draft["id"], "97.50")
    assert opened.status_code == 201 and opened.json()["status"] == "open"


def test_rate_on_request_product_snapshot(client, world):
    item = catalogue.create_product(world.session, product_code=f"ROR-{world.suffix}", name="Unpriced",
                                    category=f"cat-{world.suffix}", uom="KG")
    missing_currency = _start(client, world, item)
    assert missing_currency.status_code == 422
    body = _start(client, world, item, currency="INR").json()
    assert body["benchmark"]["state"] == "rate_on_request" and body["benchmark"]["value"] is None
    assert body["currency"] == "INR" and body["status"] == "open"


def test_access_control(client, world, product):
    negotiation_id = _start(client, world, product).json()["id"]
    other = _other_buyer(world)
    assert client.get(f"{NEGOTIATIONS}/{negotiation_id}", headers={"X-Demo-User": other.email}).status_code == 404
    assert negotiation_id not in [n["id"] for n in client.get(NEGOTIATIONS, headers={"X-Demo-User": other.email}).json()]
    supplier_view = client.get(f"{NEGOTIATIONS}/{negotiation_id}", headers=as_user(world, "supplier"))
    assert supplier_view.status_code == 200 and supplier_view.json()["viewerRole"] == "supplier"
    assert negotiation_id in [n["id"] for n in client.get(NEGOTIATIONS, headers=as_user(world, "supplier")).json()]
    # Pricing admins are not negotiation participants.
    assert client.get(NEGOTIATIONS, headers=as_user(world, "alice")).status_code == 403
    assert client.get(NEGOTIATIONS).status_code == 401
    # Suppliers cannot start negotiations.
    started = client.post(NEGOTIATIONS, json={"productCode": product.product_code, "quantity": "1"},
                          headers=as_user(world, "supplier"))
    assert started.status_code == 403


def test_offer_counter_versioning_and_turns(client, world, product):
    negotiation_id = _start(client, world, product).json()["id"]
    own_turn = _offer(client, world, "buyer", negotiation_id, "98.50")
    assert own_turn.status_code == 409 and own_turn.json()["error"]["code"] == "AWAITING_COUNTERPARTY"

    countered = _offer(client, world, "supplier", negotiation_id, "100.10", message="Counter")
    assert countered.status_code == 201 and countered.json()["status"] == "countered"
    third = _offer(client, world, "buyer", negotiation_id, "99.00", quantity="10000").json()
    assert [(v["versionNumber"], v["offeredBy"], v["offeredPrice"]["amount"], v["quantity"]) for v in third["versions"]] == [
        (1, "buyer", "98.0000", "12000"), (2, "supplier", "100.1000", "12000"), (3, "buyer", "99.0000", "10000"),
    ]
    assert third["status"] == "countered" and third["awaiting"] == "supplier"

    wrong_currency = _offer(client, world, "supplier", negotiation_id, "1.2", currency="USD")
    assert wrong_currency.status_code == 422 and wrong_currency.json()["error"]["code"] == "CURRENCY_OR_UNIT_MISMATCH"


def test_versions_are_immutable(client, world, product):
    negotiation_id = _start(client, world, product).json()["id"]
    with pytest.raises(DBAPIError, match="immutable"), world.session.begin_nested():
        world.session.execute(text("UPDATE negotiation_versions SET offered_price = 1 WHERE negotiation_id = :id"),
                              {"id": negotiation_id})
    with pytest.raises(DBAPIError, match="immutable"), world.session.begin_nested():
        world.session.execute(text("DELETE FROM negotiation_versions WHERE negotiation_id = :id"), {"id": negotiation_id})
    with pytest.raises(DBAPIError, match="immutable"), world.session.begin_nested():
        world.session.execute(text("UPDATE negotiations SET benchmark_rate_snapshot = 1 WHERE id = :id"),
                              {"id": negotiation_id})


def test_accept_sets_negotiated_price_from_accepted_version(client, world, product):
    negotiation_id = _start(client, world, product).json()["id"]
    _offer(client, world, "supplier", negotiation_id, "99.10", quantity="11000")
    own = client.post(f"{NEGOTIATIONS}/{negotiation_id}/accept", headers=as_user(world, "supplier"))
    assert own.status_code == 409 and own.json()["error"]["code"] == "AWAITING_COUNTERPARTY"

    accepted = client.post(f"{NEGOTIATIONS}/{negotiation_id}/accept", headers=as_user(world, "buyer"))
    assert accepted.status_code == 200
    body = accepted.json()
    latest = body["versions"][-1]
    assert body["status"] == "accepted" and body["closedAt"]
    assert body["negotiated"] == {"priceKind": "negotiated_price", "versionNumber": latest["versionNumber"],
                                  "price": latest["offeredPrice"], "quantity": "11000", "uom": "KG"}
    assert body["benchmark"]["value"]["amount"] == "99.4000"
    stored = world.session.get(Negotiation, uuid.UUID(body["id"]))
    assert stored.accepted_version_id == service.negotiated_version(stored).id
    assert service.negotiated_version(stored).offered_price == Decimal("99.1000")


def test_reject_and_cancel(client, world, product):
    rejected_id = _start(client, world, product).json()["id"]
    rejected = client.post(f"{NEGOTIATIONS}/{rejected_id}/reject", json={"reason": "Too low"},
                           headers=as_user(world, "supplier"))
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert rejected.json()["closedReason"] == "Too low" and rejected.json()["negotiated"] is None

    cancelled_id = _start(client, world, product).json()["id"]
    by_supplier = client.post(f"{NEGOTIATIONS}/{cancelled_id}/cancel", headers=as_user(world, "supplier"))
    assert by_supplier.status_code == 403
    cancelled = client.post(f"{NEGOTIATIONS}/{cancelled_id}/cancel", headers=as_user(world, "buyer"))
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"


@pytest.mark.parametrize("close", ["accept", "reject", "cancel"])
def test_terminal_negotiations_are_protected(client, world, product, close):
    negotiation_id = _start(client, world, product).json()["id"]
    actor = "buyer" if close == "cancel" else "supplier"
    if close == "accept":
        _offer(client, world, "supplier", negotiation_id, "99.00")
        actor = "buyer"
    assert client.post(f"{NEGOTIATIONS}/{negotiation_id}/{close}", headers=as_user(world, actor)).status_code == 200

    for key in ("buyer", "supplier"):
        offer = _offer(client, world, key, negotiation_id, "97.00")
        assert offer.status_code == 409 and offer.json()["error"]["code"] == "NEGOTIATION_CLOSED"
    for path, key in (("accept", "buyer"), ("reject", "supplier"), ("cancel", "buyer")):
        again = client.post(f"{NEGOTIATIONS}/{negotiation_id}/{path}", headers=as_user(world, key))
        assert again.status_code == 409 and again.json()["error"]["code"] == "NEGOTIATION_CLOSED"
    with pytest.raises(DBAPIError, match="final"), world.session.begin_nested():
        world.session.execute(text("UPDATE negotiations SET status = 'open', closed_at = NULL WHERE id = :id"),
                              {"id": negotiation_id})


def test_service_invalid_transitions(world, product):
    buyer, supplier = world.actors["buyer"], world.actors["supplier"]
    draft = service.create_negotiation(world.session, buyer, product_code=product.product_code, quantity=Decimal("5"),
                                       supplier_user_id=world.users["supplier"].id)
    with pytest.raises(InvalidStateTransition):
        service.reject_offer(world.session, buyer, draft.id)
    with pytest.raises(NotFound):
        service.make_offer(world.session, supplier, draft.id, price=Decimal("1"))
    service.cancel_negotiation(world.session, buyer, draft.id)
    with pytest.raises(NegotiationClosed):
        service.make_offer(world.session, buyer, draft.id, price=Decimal("1"))
    active = service.create_negotiation(world.session, buyer, product_code=product.product_code, quantity=Decimal("5"),
                                        offered_price=Decimal("90"), supplier_user_id=world.users["supplier"].id)
    with pytest.raises(AwaitingCounterparty):
        service.accept_offer(world.session, buyer, active.id)


def test_later_benchmark_changes_do_not_alter_negotiation(client, world, product):
    negotiation_id = _start(client, world, product).json()["id"]
    before = client.get(f"{NEGOTIATIONS}/{negotiation_id}", headers=as_user(world, "buyer")).json()

    newer = _publish(world, "105.00", days_ago=0)
    pricing_service.withdraw_benchmark(world.session, world.actors["bob"], newer.id, reason="Revised circular")
    after = client.get(f"{NEGOTIATIONS}/{negotiation_id}", headers=as_user(world, "buyer")).json()
    assert after["benchmark"] == before["benchmark"]
    assert after["benchmark"]["value"]["amount"] == "99.4000" and after["benchmark"]["state"] == "fresh"


def test_negotiation_response_has_no_producer_or_source_data(client, world, product):
    world.ingest(business_today(utcnow()) - timedelta(days=2), [world.row(1, "99.40"), world.row(2, "99.00", producer="B")])
    negotiation_id = _start(client, world, product).json()["id"]
    _offer(client, world, "supplier", negotiation_id, "99.20")
    for key in ("buyer", "supplier"):
        keys, values = _flatten(client.get(f"{NEGOTIATIONS}/{negotiation_id}", headers=as_user(world, key)).json())
        assert not [k for k in keys if "producer" in k.lower() or "source" in k.lower()]
        forbidden = {p.code for p in world.producers.values()} | {p.name for p in world.producers.values()}
        forbidden |= {world.erp_source.code, world.manual_source.code, "RAF-1", "Plant"}
        assert not [v for v in values if any(f in v for f in forbidden)]
