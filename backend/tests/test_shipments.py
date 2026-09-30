"""Shipment facts are what the supplier typed. Delay uses a stored required date only."""

from datetime import timedelta

from app.core.clock import business_today
from app.models.order import Order
from tests.test_api import as_user
from tests.test_order_tracking import _move, _order, _tracking
from tests.test_orders import product  # noqa: F401

ORDERS = "/api/v1/orders"


def _keys(value):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append(key)
            found.extend(_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_keys(item))
    return found


def _ready(client, world, product):
    order_id = _order(client, world, product)
    for step in ("confirmed", "processing", "ready"):
        assert _move(client, world, order_id, step).status_code == 200
    return order_id


def test_delivered_without_lr_has_no_invented_shipment(client, world, product):
    order_id = _ready(client, world, product)
    dispatched = _move(client, world, order_id, "dispatched")
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["shipment"] == {
        "lrNumber": None, "transporter": None, "vehicle": None, "eta": None,
    }
    assert _move(client, world, order_id, "in_transit").status_code == 200
    delivered = _move(client, world, order_id, "delivered")
    assert delivered.status_code == 200, delivered.text
    view = _tracking(client, world, order_id).json()
    assert view["status"] == "delivered"
    assert view["shipment"]["lrNumber"] is None
    assert view["delayed"] is False and view["requiredBy"] is None and view["pod"] is None
    names = [key.lower() for key in _keys(view)]
    assert "latitude" not in names and "longitude" not in names


def test_lr_and_eta_are_visible_to_both_parties(client, world, product):
    order_id = _ready(client, world, product)
    dispatched = client.post(f"{ORDERS}/{order_id}/status", json={
        "toStatus": "dispatched", "lrNumber": "LR-100", "transporter": "Roadline",
        "vehicle": "GJ01AB1234", "eta": "2026-10-05",
    }, headers=as_user(world, "supplier"))
    assert dispatched.status_code == 200, dispatched.text
    for key in ("buyer", "supplier"):
        shipment = _tracking(client, world, order_id, key).json()["shipment"]
        assert shipment["lrNumber"] == "LR-100"
        assert shipment["transporter"] == "Roadline"
        assert shipment["vehicle"] == "GJ01AB1234"
        assert shipment["eta"] == "2026-10-05"
    early = client.post(f"{ORDERS}/{order_id}/status", json={
        "toStatus": "in_transit", "lrNumber": "LR-200",
    }, headers=as_user(world, "supplier"))
    assert early.status_code == 422
    updated = client.post(f"{ORDERS}/{order_id}/shipment", json={
        "lrNumber": "LR-200", "transporter": "Roadline", "vehicle": "GJ01AB1234", "eta": "2026-10-06",
    }, headers=as_user(world, "supplier"))
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "dispatched"
    assert updated.json()["shipment"]["lrNumber"] == "LR-200"
    assert _tracking(client, world, order_id).json()["shipment"]["eta"] == "2026-10-06"
    assert client.post(f"{ORDERS}/{order_id}/shipment", json={"lrNumber": "LR-9"},
                       headers=as_user(world, "buyer")).status_code == 403


def test_delay_uses_only_a_stored_required_date(client, world, product):
    order_id = _ready(client, world, product)
    order = world.session.get(Order, order_id)
    order.negotiation.required_by = business_today() + timedelta(days=2)
    world.session.flush()
    upcoming = _tracking(client, world, order_id).json()
    assert upcoming["delayed"] is False and upcoming["requiredBy"] == str(order.negotiation.required_by)

    order.negotiation.required_by = business_today() - timedelta(days=1)
    world.session.flush()
    assert _tracking(client, world, order_id).json()["delayed"] is True

    for step in ("dispatched", "in_transit", "delivered"):
        assert _move(client, world, order_id, step).status_code == 200
    assert _tracking(client, world, order_id).json()["delayed"] is False


def test_pod_link_uses_the_order_document(client, world, product):
    order_id = _ready(client, world, product)
    assert _move(client, world, order_id, "dispatched").status_code == 200
    uploaded = client.post(
        f"{ORDERS}/{order_id}/documents",
        data={"documentType": "pod"},
        files={"file": ("pod.pdf", b"pod-bytes", "application/pdf")},
        headers=as_user(world, "supplier"),
    )
    assert uploaded.status_code == 201, uploaded.text
    pod = _tracking(client, world, order_id).json()["pod"]
    assert pod["filename"] == "pod.pdf" and pod["id"] == uploaded.json()["id"]
    before = client.post(f"{ORDERS}/{_order(client, world, product)}/shipment", json={"lrNumber": "LR-1"},
                         headers=as_user(world, "supplier"))
    assert before.status_code == 409
