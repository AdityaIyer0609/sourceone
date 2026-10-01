from decimal import Decimal

from app.suppliers.ranking import comparison_factor
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_negotiations import product  # noqa: F401


def _rates(**overrides):
    base = {
        "acceptance": {"available": False, "count": 0, "total": 0, "percent": None},
        "order_cancellation": {"available": False, "count": 0, "total": 0, "percent": None},
        "quality": {"available": False, "count": 0, "total": 0, "percent": None},
        "response_time": {"available": False, "sample_count": 0, "average_hours": None},
    }
    base.update(overrides)
    return base


def test_no_history_is_neutral():
    factor, notes = comparison_factor(_rates())
    assert factor == Decimal("1.0000")
    assert notes == ["No history yet"]


def test_one_accepted_negotiation_does_not_change_the_factor():
    factor, notes = comparison_factor(_rates(acceptance={
        "available": True, "count": 1, "total": 1, "percent": "100.00",
    }))
    assert factor == Decimal("1.0000")
    assert notes == ["No history yet"]


def test_weak_acceptance_raises_the_factor_and_a_strong_record_lowers_it():
    weak, notes = comparison_factor(_rates(acceptance={
        "available": True, "count": 2, "total": 10, "percent": "20.00",
    }))
    assert weak == Decimal("1.0800")
    assert any("20.00%" in note for note in notes)
    strong, strong_notes = comparison_factor(_rates(acceptance={
        "available": True, "count": 8, "total": 10, "percent": "80.00",
    }))
    assert strong == Decimal("0.9700")
    assert "Strong acceptance record" in strong_notes


def test_factor_stays_inside_the_cap():
    factor, _notes = comparison_factor(_rates(
        acceptance={"available": True, "count": 0, "total": 10, "percent": "0.00"},
        order_cancellation={"available": True, "count": 10, "total": 10, "percent": "100.00"},
        quality={"available": True, "count": 3, "total": 3, "percent": "100.00"},
        response_time={"available": True, "sample_count": 5, "average_hours": "90.00"},
    ))
    assert factor == Decimal("1.2500")


def test_saved_lane_ranks_the_supplier_and_per_km_is_only_a_fallback(monkeypatch, client, world, product):
    org = world.users["supplier"].organisation
    org.dispatch_pin = "560001"
    org.dispatch_label = "Bengaluru"
    world.session.flush()
    listing = _create(client, world, product, askingPrice="100.0000").json()
    saved = client.post("/api/v1/supplier-freight/lanes", json={
        "destinationPin": "400001", "destinationLabel": "Mumbai", "ratePerKg": "2.0000", "currency": "INR",
    }, headers=as_user(world, "supplier"))
    assert saved.status_code == 201, saved.text
    client.put("/api/v1/supplier-freight/km-rate", json={
        "ratePerKm": "10.0000", "currency": "INR",
    }, headers=as_user(world, "supplier"))

    def _distance(_session, origin, destination, _provider):
        assert origin == "560001" and destination == "400002"
        return Decimal("100"), "test"

    monkeypatch.setattr("app.suppliers.freight.road_distance", _distance)
    lane = client.get(
        f"/api/v1/products/{product.product_code}/supplier-matches",
        headers=as_user(world, "buyer"),
        params={"quantity": "500", "uom": "KG", "destinationPin": "400001"},
    )
    assert lane.status_code == 200, lane.text
    [row] = lane.json()["matches"]
    assert row["supplierUserId"] == listing["supplierUserId"]
    assert row["comparison"]["basis"] == "lane"
    assert row["comparison"]["freight"]["amount"] == "1000.0000"
    assert row["comparison"]["place"] == 1
    assert row["comparison"]["factor"] == "1.0000"
    fallback = client.get(
        f"/api/v1/products/{product.product_code}/supplier-matches",
        headers=as_user(world, "buyer"),
        params={"quantity": "500", "uom": "KG", "destinationPin": "400002"},
    )
    assert fallback.json()["matches"][0]["comparison"]["basis"] == "per_km"
    assert fallback.json()["matches"][0]["comparison"]["freight"]["amount"] == "1000.0000"
