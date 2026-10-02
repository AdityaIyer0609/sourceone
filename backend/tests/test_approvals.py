"""A company threshold does not hold an order. The buyer places it at any material total."""

import pytest
from sqlalchemy import func, select

from app.catalogue import products as catalogue
from app.models.identity import Role, User, UserRole
from app.models.order import Order
from tests.test_api import as_actor
from tests.test_negotiations import _publish
from tests.test_orders import _negotiation, _place


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


def test_above_the_threshold_still_places_the_order(client, world, product):
    approver = _approver(world)
    _threshold(client, approver, "500.00")
    negotiation = _negotiation(world, product, price="100", counter="100", quantity="10")
    placed = _place(client, world, negotiation)
    assert placed.status_code == 201, placed.text
    assert placed.json()["totalValue"]["amount"] == "1000.00"
    assert _orders_for(world, negotiation.id) == 1
    assert client.get("/api/v1/order-approvals", headers=as_actor(approver)).json() == []
