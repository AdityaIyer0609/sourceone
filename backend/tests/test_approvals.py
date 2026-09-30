"""An order above the company material threshold waits for a different person to approve it."""

import pytest
from sqlalchemy import func, select

from app.catalogue import products as catalogue
from app.models.identity import Role, User, UserRole
from app.models.order import Order
from tests.test_api import as_actor, as_user
from tests.test_negotiations import _publish
from tests.test_orders import _negotiation, _place

ORDERS = "/api/v1/orders"


@pytest.fixture
def product(world):
    _publish(world, "99.40")
    item = catalogue.create_product(
        world.session, product_code=f"APR-{world.suffix}", name="Approval PP",
        category=f"cat-{world.suffix}", uom="KG",
    )
    catalogue.map_rate_series(world.session, item, world.series["inr"])
    return item


def _approver(world, organisation_id=None, name="Company Approver"):
    organisation_id = organisation_id or world.users["buyer"].organisation_id
    user = User(
        email=f"{name.split()[0].lower()}-{world.suffix.lower()}@test.local", full_name=name,
        organisation_id=organisation_id,
    )
    world.session.add(user)
    world.session.flush()
    role = world.session.scalar(select(Role).where(Role.code == "approver"))
    world.session.add(UserRole(user_id=user.id, role_id=role.id))
    world.session.flush()
    return user


def _threshold(client, user, amount):
    response = client.put(
        "/api/v1/organisation/threshold",
        json={"amount": amount, "currency": "INR"},
        headers=as_actor(user),
    )
    assert response.status_code == 200, response.text
    return response


def _orders_for(world, negotiation_id) -> int:
    return world.session.scalar(
        select(func.count()).select_from(Order).where(Order.negotiation_id == negotiation_id)
    ) or 0


def test_below_or_equal_to_the_threshold_still_places_the_order(client, world, product):
    approver = _approver(world)
    _threshold(client, approver, "1000.00")
    negotiation = _negotiation(world, product, price="100", counter="100", quantity="10")
    placed = _place(client, world, negotiation)
    assert placed.status_code == 201, placed.text
    assert placed.json()["totalValue"]["amount"] == "1000.00"
    assert _orders_for(world, negotiation.id) == 1


def test_above_the_threshold_creates_no_order_until_someone_else_approves(client, world, product):
    approver = _approver(world)
    _threshold(client, approver, "500.00")
    buyer_role = world.session.scalar(select(Role).where(Role.code == "approver"))
    world.session.add(UserRole(user_id=world.users["buyer"].id, role_id=buyer_role.id))
    world.session.flush()
    negotiation = _negotiation(world, product, price="100", counter="100", quantity="10")
    submitted = _place(client, world, negotiation)
    assert submitted.status_code == 202, submitted.text
    body = submitted.json()
    assert body["status"] == "pending"
    assert body["amount"]["amount"] == "1000.0000"
    assert body["threshold"]["amount"] == "500.0000"
    assert body["negotiationId"] == str(negotiation.id)
    assert _orders_for(world, negotiation.id) == 0
    world.session.refresh(negotiation)
    assert negotiation.status == "accepted"

    own = client.post(f"/api/v1/order-approvals/{body['id']}/approve", headers=as_user(world, "buyer"))
    assert own.status_code == 403 and own.json()["error"]["code"] == "FOUR_EYES_REQUIRED"
    assert _orders_for(world, negotiation.id) == 0

    approved = client.post(f"/api/v1/order-approvals/{body['id']}/approve", headers=as_actor(approver))
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["decidedBy"] == "Company Approver"
    assert _orders_for(world, negotiation.id) == 1
    order = client.get(ORDERS, headers=as_user(world, "buyer")).json()[0]
    assert order["totalValue"]["amount"] == "1000.00"
    assert order["agreedPrice"]["unitPrice"]["amount"] == "100.0000"
    audit = client.get("/api/v1/order-approvals", headers=as_actor(approver)).json()
    assert audit[0]["negotiationId"] == str(negotiation.id)
    assert audit[0]["submittedBy"] == "Buyer"
    assert audit[0]["decidedBy"] == "Company Approver"


def test_declining_leaves_the_negotiation_accepted_and_rejecting_the_deal_cancels_it(client, world, product):
    approver = _approver(world)
    _threshold(client, approver, "500.00")
    first = _negotiation(world, product, price="100", counter="100", quantity="10")
    pending = _place(client, world, first).json()
    declined = client.post(
        f"/api/v1/order-approvals/{pending['id']}/decline",
        json={"note": "Ask for a lower price"},
        headers=as_actor(approver),
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"
    world.session.refresh(first)
    assert first.status == "accepted"
    assert _orders_for(world, first.id) == 0
    again = _place(client, world, first)
    assert again.status_code == 202

    second = _negotiation(world, product, price="100", counter="110", quantity="10")
    deal = _place(client, world, second).json()
    rejected = client.post(
        f"/api/v1/order-approvals/{deal['id']}/reject-deal",
        json={"note": "Do not buy this"},
        headers=as_actor(approver),
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "deal_rejected"
    world.session.refresh(second)
    assert second.status == "cancelled"
    assert _orders_for(world, second.id) == 0


def test_an_approver_outside_the_company_cannot_see_the_request(client, world, product):
    from app.models.identity import Organisation

    approver = _approver(world)
    _threshold(client, approver, "500.00")
    negotiation = _negotiation(world, product, price="100", counter="100", quantity="10")
    pending = _place(client, world, negotiation).json()
    other_org = Organisation(code=f"OTH-{world.suffix}", name="Other company", org_type="buyer")
    world.session.add(other_org)
    world.session.flush()
    outsider = _approver(world, other_org.id, name="Outside Approver")
    hidden = client.get("/api/v1/order-approvals", headers=as_actor(outsider))
    assert hidden.status_code == 200 and hidden.json() == []
    refused = client.post(f"/api/v1/order-approvals/{pending['id']}/approve", headers=as_actor(outsider))
    assert refused.status_code == 404
