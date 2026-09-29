"""Sign-in is email and password. The demo header is not accepted."""

from app.identity.passwords import hash_password
from app.seed.demo import DEMO_PASSWORD
from tests.test_api import as_user


def test_login_issues_a_token_and_hides_the_password_hash(client, world):
    user = world.users["buyer"]
    user.password_hash = hash_password(DEMO_PASSWORD)
    world.session.flush()
    wrong = client.post("/api/v1/auth/login", json={"email": user.email, "password": "nope"})
    assert wrong.status_code == 401
    logged_in = client.post("/api/v1/auth/login", json={"email": user.email.upper(), "password": DEMO_PASSWORD})
    assert logged_in.status_code == 200, logged_in.text
    body = logged_in.json()
    assert body["tokenType"] == "bearer" and body["accessToken"]
    assert "password" not in body and "passwordHash" not in str(body)
    assert body["user"]["email"] == user.email and "buyer" in body["user"]["roles"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['accessToken']}"})
    assert me.status_code == 200 and me.json()["email"] == user.email
    assert client.get("/api/v1/benchmarks", headers={"X-Demo-User": user.email}).status_code == 401
    assert client.get("/api/v1/benchmarks", headers=as_user(world, "buyer")).status_code == 200


def test_system_account_cannot_sign_in(client, world):
    user = world.users["system"]
    user.password_hash = hash_password(DEMO_PASSWORD)
    world.session.flush()
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": DEMO_PASSWORD})
    assert response.status_code == 401
