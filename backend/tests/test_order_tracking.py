import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models.order import OrderStatusEvent
from app.orders.constants import FULFILMENT_FLOW
from tests.test_api import as_user
from tests.test_negotiations import _other_buyer
from tests.test_orders import ORDERS, _negotiation, _place, product  # noqa: F401  (fixture)


def _order(client, world, product):
    response = _place(client, world, _negotiation(world, product))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _move(client, world, order_id, to_status, key="supplier", note=None):
    return client.post(f"{ORDERS}/{order_id}/status", json={"toStatus": to_status, "note": note},
                       headers=as_user(world, key))


def _tracking(client, world, order_id, key="buyer"):
    return client.get(f"{ORDERS}/{order_id}/tracking", headers=as_user(world, key))


def _events(world, order_id):
    return world.session.scalars(
        select(OrderStatusEvent).where(OrderStatusEvent.order_id == order_id).order_by(OrderStatusEvent.created_at)
    ).all()


def test_supplier_progresses_through_full_flow(client, world, product):
    order_id = _order(client, world, product)
    tracking = _tracking(client, world, order_id, "supplier").json()
    assert tracking["status"] == "placed" and tracking["nextStatus"] == "confirmed" and tracking["canProgress"]
    assert [s["status"] for s in tracking["steps"]] == list(FULFILMENT_FLOW)

    for step in FULFILMENT_FLOW[1:]:
        response = _move(client, world, order_id, step, note=f"now {step}")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == step

    final = response.json()
    assert final["nextStatus"] is None and final["canProgress"] is False
    assert [s["state"] for s in final["steps"]] == ["completed"] * 5 + ["current"]
    assert final["steps"][2]["note"] == "now processing" and final["steps"][2]["changedBy"]
    assert client.get(f"{ORDERS}/{order_id}", headers=as_user(world, "buyer")).json()["status"] == "delivered"


def test_skipping_and_backward_moves_are_rejected(client, world, product):
    order_id = _order(client, world, product)
    skipped = _move(client, world, order_id, "processing")
    assert skipped.status_code == 409 and skipped.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert _move(client, world, order_id, "confirmed").status_code == 200
    assert _move(client, world, order_id, "placed").status_code == 409
    assert _move(client, world, order_id, "confirmed").status_code == 409
    assert _move(client, world, order_id, "cancelled").status_code == 409
    assert _move(client, world, order_id, "shipped").status_code == 422
    assert [e.to_status for e in _events(world, order_id)] == ["placed", "confirmed"]


def test_only_assigned_supplier_updates_and_buyer_is_read_only(client, world, product):
    order_id = _order(client, world, product)
    buyer_attempt = _move(client, world, order_id, "confirmed", key="buyer")
    assert buyer_attempt.status_code == 403 and buyer_attempt.json()["error"]["code"] == "PERMISSION_DENIED"

    buyer_view = _tracking(client, world, order_id, "buyer").json()
    assert buyer_view["viewerRole"] == "buyer" and buyer_view["canProgress"] is False
    assert buyer_view["nextStatus"] is None

    for key in ("alice", "bob", "platform"):
        assert _move(client, world, order_id, "confirmed", key=key).status_code == 403
        assert _tracking(client, world, order_id, key).status_code == 403
    assert [e.to_status for e in _events(world, order_id)] == ["placed"]


def test_tracking_hidden_from_other_parties(client, world, product):
    order_id = _order(client, world, product)
    other = _other_buyer(world)
    assert client.get(f"{ORDERS}/{order_id}/tracking", headers={"X-Demo-User": other.email}).status_code == 404
    assert client.post(f"{ORDERS}/{order_id}/status", json={"toStatus": "confirmed"},
                       headers={"X-Demo-User": other.email}).status_code == 404
    assert client.get(f"{ORDERS}/{order_id}/tracking").status_code == 401


def test_cancelled_and_delivered_orders_cannot_progress(client, world, product):
    cancelled = _order(client, world, product)
    _move(client, world, cancelled, "confirmed")
    assert client.post(f"{ORDERS}/{cancelled}/cancel", json={"reason": "No longer needed"},
                       headers=as_user(world, "buyer")).status_code == 200
    blocked = _move(client, world, cancelled, "processing")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "ORDER_CLOSED"

    view = _tracking(client, world, cancelled).json()
    assert view["status"] == "cancelled" and view["nextStatus"] is None
    states = {s["status"]: s["state"] for s in view["steps"]}
    assert states == {"placed": "completed", "confirmed": "completed", "processing": "pending", "ready": "pending",
                      "dispatched": "pending", "delivered": "pending", "cancelled": "current"}
    assert view["events"][-1]["note"] == "No longer needed" and view["events"][-1]["changedByRole"] == "buyer"

    delivered = _order(client, world, product)
    for step in FULFILMENT_FLOW[1:]:
        _move(client, world, delivered, step)
    after = _move(client, world, delivered, "delivered")
    assert after.status_code == 409 and after.json()["error"]["code"] == "ORDER_CLOSED"
    assert len(_events(world, delivered)) == len(FULFILMENT_FLOW)


def test_every_transition_creates_immutable_event(client, world, product):
    order_id = _order(client, world, product)
    _move(client, world, order_id, "confirmed", note="  Slot booked  ")
    _move(client, world, order_id, "processing")
    events = _events(world, order_id)
    assert [(e.from_status, e.to_status) for e in events] == [
        (None, "placed"), ("placed", "confirmed"), ("confirmed", "processing"),
    ]
    assert events[0].changed_by_user_id == world.users["buyer"].id
    assert events[1].changed_by_user_id == world.users["supplier"].id
    assert events[1].note == "Slot booked" and events[2].note is None

    with pytest.raises(DBAPIError, match="immutable"), world.session.begin_nested():
        world.session.execute(text("UPDATE order_status_events SET note = 'edited' WHERE id = :id"), {"id": events[1].id})
    with pytest.raises(DBAPIError, match="immutable"), world.session.begin_nested():
        world.session.execute(text("DELETE FROM order_status_events WHERE id = :id"), {"id": events[0].id})


def test_database_rejects_events_that_break_the_history(client, world, product):
    order_id = _order(client, world, product)
    insert = text(
        "INSERT INTO order_status_events (id, order_id, from_status, to_status, changed_by_user_id, created_at) "
        "VALUES (gen_random_uuid(), :order, :from_status, :to_status, :user, now())"
    )
    params = {"order": order_id, "user": world.users["supplier"].id}
    with pytest.raises(DBAPIError, match="current status"), world.session.begin_nested():
        world.session.execute(insert, {**params, "from_status": "placed", "to_status": "confirmed"})

    with pytest.raises(DBAPIError, match="without a status event"), world.session.begin_nested():
        world.session.execute(text("UPDATE orders SET status = 'confirmed' WHERE id = :id"), {"id": order_id})
        world.session.execute(text("SET CONSTRAINTS orders_status_has_event IMMEDIATE"))
    world.session.execute(text("SET CONSTRAINTS orders_status_has_event DEFERRED"))


def test_tracking_history_is_ordered_and_matches_current_status(client, world, product):
    order_id = _order(client, world, product)
    for step in ("confirmed", "processing", "ready"):
        _move(client, world, order_id, step)
    view = _tracking(client, world, order_id, "buyer").json()
    assert [e["toStatus"] for e in view["events"]] == ["placed", "confirmed", "processing", "ready"]
    stamps = [e["createdAt"] for e in view["events"]]
    assert stamps == sorted(stamps)
    assert view["events"][-1]["toStatus"] == view["status"] == "ready"
    assert view["lastUpdatedAt"] == stamps[-1]
    assert [s["state"] for s in view["steps"]] == ["completed", "completed", "completed", "current", "pending", "pending"]
    assert all(s["at"] is None for s in view["steps"][4:])
