import json
import os
from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import get_settings
from app.freight.distance import GeoapifyDistanceProvider
from app.models.freight import RoadDistance
from tests.test_api import as_user
from tests.test_freight import _estimate, _origin, _rule
from tests.test_listings import _create
from tests.test_negotiations import product  # noqa: F401

RATES = "/api/v1/admin/freight/distance-rates"


class FakeDistance:
    def __init__(self, kilometres="120.500", fail=False):
        self.calls = 0
        self.kilometres = Decimal(kilometres)
        self.fail = fail

    def coordinates(self, pin):
        self.calls += 1
        if self.fail:
            return None
        return Decimal("23.022500"), Decimal("72.571400")

    def driving_km(self, origin, destination):
        self.calls += 1
        if self.fail:
            return None
        return self.kilometres


def _rate(client, world, **extra):
    body = {"currency": "INR", "ratePerKm": "2.0000", "minimumFreight": None, "isActive": True, **extra}
    return client.put(RATES, json=body, headers=as_user(world, "platform"))


def _patch(monkeypatch, provider):
    monkeypatch.setattr("app.freight.service.get_distance_provider", lambda: provider)


def test_saved_lane_stays_separate_from_the_road_distance_option(monkeypatch, client, world, product):
    provider = FakeDistance()
    _patch(monkeypatch, provider)
    _origin(world, pin="682016", label="Kochi")
    listing = _create(client, world, product, askingPrice="100.2500").json()
    assert _rate(client, world).status_code == 200
    created = _rule(client, world, originPin="682016", originLabel="Kochi", destinationPin="110001", destinationLabel="Delhi", ratePerKg="1.2500", minimumFreight="1500")
    assert created.status_code == 201, created.text
    hidden = _estimate(client, world, product, listing, quantity="1000", pin="110001")
    assert hidden.json()["match"] == "lane" and hidden.json()["roadDistanceKm"] is None
    assert provider.calls == 0
    estimate = _estimate(client, world, product, listing, quantity="1000", pin="110001", include_distance=True)
    assert estimate.status_code == 200, estimate.text
    body = estimate.json()
    assert body["match"] == "lane"
    assert body["freight"] == {"amount": "1500.0000", "currency": "INR"}
    assert body["distanceStatus"] == "estimated"
    assert body["distanceFreight"] == {"amount": "241.0000", "currency": "INR"}
    assert body["roadDistanceKm"] == "120.500"
    assert body["distanceRatePerKm"] == "2.0000"


def test_road_distance_prices_only_from_the_configured_rate(monkeypatch, client, world, product):
    provider = FakeDistance()
    _patch(monkeypatch, provider)
    _origin(world, pin="682016", label="Kochi")
    listing = _create(client, world, product, askingPrice="100.2500").json()
    saved = _rate(client, world, minimumFreight="100")
    assert saved.status_code == 200, saved.text
    first = _estimate(client, world, product, listing, quantity="1000", pin="110001", include_distance=True)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["freightStatus"] == "on_request"
    assert body["freight"] is None
    assert body["distanceStatus"] == "estimated"
    assert body["distanceFreight"] == {"amount": "241.0000", "currency": "INR"}
    assert body["roadDistanceKm"] == "120.500"
    assert body["distanceSource"] == "geoapify"
    assert "Estimated road distance" in body["distanceNote"]
    assert body["supplierAskingPrice"] == {"amount": "100.2500", "currency": "INR"}
    assert body["materialValue"] == {"amount": "100250.0000", "currency": "INR"}
    calls = provider.calls
    assert calls == 3
    second = _estimate(client, world, product, listing, quantity="1000", pin="110001", include_distance=True).json()
    assert second["distanceSource"] == "cache"
    assert second["distanceFreight"] == body["distanceFreight"]
    assert provider.calls == calls


def test_same_origin_pin_is_not_resolved_again(monkeypatch, client, world, product):
    provider = FakeDistance()
    _patch(monkeypatch, provider)
    _origin(world, pin="682016", label="Kochi")
    listing = _create(client, world, product).json()
    assert _rate(client, world).status_code == 200
    _estimate(client, world, product, listing, pin="110001", include_distance=True)
    after_first = provider.calls
    _estimate(client, world, product, listing, pin="560076", include_distance=True)
    assert provider.calls == after_first + 2


def test_builtin_rate_per_km_prices_the_road_option(monkeypatch, client, world, product):
    _patch(monkeypatch, FakeDistance(kilometres="10.000"))
    _origin(world, pin="682016", label="Kochi")
    listing = _create(client, world, product).json()
    assert _rate(client, world, isActive=False).status_code == 200
    body = _estimate(client, world, product, listing, pin="110001", include_distance=True).json()
    assert body["distanceRatePerKm"] == "2.0000"
    assert body["distanceFreight"] == {"amount": "20.0000", "currency": "INR"}


def test_minimum_charge_applies_to_distance_freight(monkeypatch, client, world, product):
    _patch(monkeypatch, FakeDistance(kilometres="10.000"))
    _origin(world, pin="682016", label="Kochi")
    listing = _create(client, world, product).json()
    assert _rate(client, world, ratePerKm="1.0000", minimumFreight="500").status_code == 200
    body = _estimate(client, world, product, listing, pin="110001", include_distance=True).json()
    assert body["distanceFreight"] == {"amount": "500.0000", "currency": "INR"}
    assert body["distanceMinimumApplied"] is True
    assert body["freightStatus"] == "on_request"


def test_unavailable_distance_is_on_request_and_not_stored(monkeypatch, client, world, product):
    _patch(monkeypatch, FakeDistance(fail=True))
    _origin(world, pin="682016", label="Kochi")
    listing = _create(client, world, product).json()
    assert _rate(client, world).status_code == 200
    client.put("/api/v1/admin/freight/defaults", json={
        "currency": "INR", "ratePerKg": "0.5000", "minimumFreight": None, "isActive": True,
    }, headers=as_user(world, "platform"))
    body = _estimate(client, world, product, listing, pin="110001", include_distance=True).json()
    assert body["match"] == "default"
    assert body["distanceStatus"] == "on_request"
    assert body["distanceFreight"] is None and body["roadDistanceKm"] is None
    stored = world.session.scalar(
        select(func.count()).select_from(RoadDistance).where(RoadDistance.origin_pin == "682016")
    )
    assert stored == 0


def test_missing_api_key_does_not_invent_distance(monkeypatch, client, world, product):
    _patch(monkeypatch, GeoapifyDistanceProvider(None))
    _origin(world, pin="682016", label="Kochi")
    listing = _create(client, world, product).json()
    assert _rate(client, world).status_code == 200
    body = _estimate(client, world, product, listing, pin="110001", include_distance=True).json()
    assert body["freightStatus"] == "on_request"
    assert body["distanceStatus"] == "on_request"
    assert body["roadDistanceKm"] is None


def test_geoapify_parser_uses_driving_metres_only(monkeypatch):
    class Response:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    payloads = [
        {"results": [{"lat": 23.02, "lon": 72.57}]},
        {"features": [{"properties": {"distance": 1500}}]},
    ]

    def fake_open(url, timeout=12):
        return Response(payloads.pop(0))

    monkeypatch.setattr("app.freight.distance.urlopen", fake_open)
    provider = GeoapifyDistanceProvider(SecretStr("test-key"))
    point = provider.coordinates("682016")
    assert point == (Decimal("23.020000"), Decimal("72.570000"))
    assert provider.driving_km(point, point) == Decimal("1.500")
    def unavailable(url, timeout=12):
        raise TimeoutError()

    monkeypatch.setattr("app.freight.distance.urlopen", unavailable)
    assert provider.coordinates("110001") is None
    assert provider.driving_km(point, point) is None


@pytest.mark.skipif(os.environ.get("GEOAPIFY_LIVE") != "1", reason="set GEOAPIFY_LIVE=1 to call Geoapify")
def test_live_geoapify_road_distance(client, world, product):
    key = get_settings().geoapify_api_key
    if key is None or not key.get_secret_value().strip():
        pytest.skip("GEOAPIFY_API_KEY is not set")
    _origin(world, pin="380001", label="Ahmedabad")
    listing = _create(client, world, product, askingPrice="100.2500").json()
    saved = _rate(client, world, ratePerKm="2.0000", minimumFreight=None)
    assert saved.status_code == 200, saved.text
    first = _estimate(client, world, product, listing, quantity="1000", pin="390001", include_distance=True)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["distanceStatus"] == "estimated", body["distanceNote"]
    assert body["distanceSource"] == "geoapify"
    kilometres = Decimal(body["roadDistanceKm"])
    assert Decimal("40") < kilometres < Decimal("250")
    expected = (kilometres * Decimal("2")).quantize(Decimal("0.0001"))
    assert body["distanceFreight"]["amount"] == f"{expected:.4f}"
    assert body["supplierAskingPrice"]["amount"] == "100.2500"
    assert body["freight"] != body["distanceFreight"]
    second = _estimate(client, world, product, listing, quantity="1000", pin="390001", include_distance=True).json()
    assert second["distanceSource"] == "cache"
    assert second["roadDistanceKm"] == body["roadDistanceKm"]
    assert second["freight"] == body["freight"]
