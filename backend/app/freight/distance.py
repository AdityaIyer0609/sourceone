"""Road distance for freight. Geoapify is one provider; the estimate service depends only on this interface."""

import json
from decimal import Decimal
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.freight import PinCoordinate, RoadDistance

KM = Decimal("0.001")
PROVIDER = "geoapify"


class DistanceProvider:
    """Resolves a PIN and a driving distance. Returns None when either is unavailable."""

    def coordinates(self, pin: str) -> tuple[Decimal, Decimal] | None:
        raise NotImplementedError

    def driving_km(self, origin: tuple[Decimal, Decimal], destination: tuple[Decimal, Decimal]) -> Decimal | None:
        raise NotImplementedError


class GeoapifyDistanceProvider(DistanceProvider):
    def __init__(self, api_key: SecretStr | None):
        self._key = api_key.get_secret_value().strip() if api_key is not None else ""

    def coordinates(self, pin: str) -> tuple[Decimal, Decimal] | None:
        if not self._key:
            return None
        query = urlencode({
            "text": pin,
            "filter": "countrycode:in",
            "format": "json",
            "limit": 1,
            "apiKey": self._key,
        })
        body = _get(f"https://api.geoapify.com/v1/geocode/search?{query}")
        results = body.get("results") if isinstance(body, dict) else None
        if not results:
            return None
        row = results[0]
        lat, lon = row.get("lat"), row.get("lon")
        if lat is None or lon is None:
            return None
        return _coord(lat), _coord(lon)

    def driving_km(self, origin: tuple[Decimal, Decimal], destination: tuple[Decimal, Decimal]) -> Decimal | None:
        if not self._key:
            return None
        waypoints = f"{origin[0]},{origin[1]}|{destination[0]},{destination[1]}"
        query = urlencode({"waypoints": waypoints, "mode": "drive", "apiKey": self._key})
        body = _get(f"https://api.geoapify.com/v1/routing?{query}")
        features = body.get("features") if isinstance(body, dict) else None
        if not features:
            return None
        meters = features[0].get("properties", {}).get("distance")
        if meters is None:
            return None
        kilometres = (Decimal(str(meters)) / Decimal(1000)).quantize(KM)
        return kilometres if kilometres > 0 else None


def get_distance_provider() -> DistanceProvider:
    return GeoapifyDistanceProvider(get_settings().geoapify_api_key)


def road_distance(
    session: Session, origin_pin: str, destination_pin: str, provider: DistanceProvider,
) -> tuple[Decimal, str] | None:
    """Returns (kilometres, source). Source is 'cache' or the provider name. None means unavailable.

    A PIN's coordinates are stored once. A road distance is stored once per origin PIN and
    destination PIN. A later request for that same pair does not call Geoapify. A different PIN
    in the same 3-digit zone is not given this distance; that zone is only a saved freight rule.
    """
    cached = session.scalar(
        select(RoadDistance).where(
            RoadDistance.origin_pin == origin_pin,
            RoadDistance.destination_pin == destination_pin,
        )
    )
    if cached is not None:
        return cached.distance_km, "cache"
    origin = _coordinates(session, origin_pin, provider)
    destination = _coordinates(session, destination_pin, provider)
    if origin is None or destination is None:
        return None
    kilometres = provider.driving_km(origin, destination)
    if kilometres is None:
        return None
    session.add(RoadDistance(
        origin_pin=origin_pin,
        destination_pin=destination_pin,
        distance_km=kilometres,
        provider=PROVIDER,
    ))
    session.flush()
    return kilometres, PROVIDER


def _coordinates(session: Session, pin: str, provider: DistanceProvider) -> tuple[Decimal, Decimal] | None:
    stored = session.scalar(select(PinCoordinate).where(PinCoordinate.pin == pin))
    if stored is not None:
        return stored.latitude, stored.longitude
    point = provider.coordinates(pin)
    if point is None:
        return None
    session.add(PinCoordinate(pin=pin, latitude=point[0], longitude=point[1]))
    session.flush()
    return point


def _coord(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _get(url: str) -> dict | None:
    try:
        with urlopen(url, timeout=12) as response:
            if getattr(response, "status", 200) != 200:
                return None
            payload = json.loads(response.read().decode())
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
        return None
    return payload if isinstance(payload, dict) else None
