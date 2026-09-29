"""Platform admins manage SourceOne users. Password hashes stay on the server."""

from sqlalchemy import select

from app.identity.passwords import hash_password
from app.models.order import Order
from app.seed.demo import DEMO_PASSWORD
from tests.test_api import as_user
from tests.test_orders import _negotiation, _place, product  # noqa: F401

USERS = "/api/v1/admin/users"


def test_platform_admin_creates_a_user_without_exposing_the_hash(client, world):
    admin = as_user(world, "platform")
    email = f"new-{world.suffix.lower()}@example.test"
    created = client.post(USERS, json={
        "fullName": "New Buyer", "email": email.upper(), "password": DEMO_PASSWORD, "role": "buyer",
    }, headers=admin)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == email and body["roles"] == ["buyer"] and body["isActive"] is True
    assert "password" not in body and "pbkdf2" not in created.text
    listed = client.get(USERS, headers=admin).json()
    assert email in {row["email"] for row in listed}
    assert "pbkdf2" not in str(listed)
    signed_in = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert signed_in.status_code == 200 and signed_in.json()["user"]["roles"] == ["buyer"]
    duplicate = client.post(USERS, json={
        "fullName": "Again", "email": email, "password": DEMO_PASSWORD, "role": "supplier",
    }, headers=admin)
    assert duplicate.status_code == 422
    assert client.get(USERS, headers=as_user(world, "alice")).status_code == 403
    assert client.post(USERS, json={
        "fullName": "Nope", "email": f"nope-{world.suffix.lower()}@example.test", "password": DEMO_PASSWORD, "role": "buyer",
    }, headers=as_user(world, "buyer")).status_code == 403


def test_deactivated_user_cannot_sign_in_and_keeps_their_records(client, world, product):
    order = _place(client, world, _negotiation(world, product)).json()
    buyer = world.users["buyer"]
    admin = as_user(world, "platform")
    changed = client.post(f"{USERS}/{buyer.id}/role", json={"role": "supplier"}, headers=admin)
    assert changed.status_code == 200, changed.text
    assert changed.json()["roles"] == ["supplier"]
    restored = client.post(f"{USERS}/{buyer.id}/role", json={"role": "buyer"}, headers=admin)
    assert restored.status_code == 200 and restored.json()["roles"] == ["buyer"]
    deactivated = client.post(f"{USERS}/{buyer.id}/active", json={"isActive": False}, headers=admin)
    assert deactivated.status_code == 200 and deactivated.json()["isActive"] is False
    assert world.session.scalar(select(Order).where(Order.id == order["id"])).buyer_user_id == buyer.id
    buyer.password_hash = hash_password(DEMO_PASSWORD)
    world.session.flush()
    assert client.post("/api/v1/auth/login", json={"email": buyer.email, "password": DEMO_PASSWORD}).status_code == 401
    assert client.post(f"{USERS}/{buyer.id}/active", json={"isActive": True}, headers=admin).status_code == 200
