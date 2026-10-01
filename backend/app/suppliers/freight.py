"""A supplier's own freight. A saved lane wins. Their per-km rate is only the fallback.

Platform lanes and the platform default are not used here.
"""

import re
import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.freight.distance import get_distance_provider, road_distance
from app.identity.service import Actor
from app.models.freight import SupplierFreightKmRate, SupplierFreightLane
from app.models.identity import Organisation, User
from app.negotiation.constants import NegotiationPermission
from app.pricing.constants import SUPPORTED_CURRENCIES

PIN = re.compile(r"^[1-9][0-9]{5}$")


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _pin(value: str, field: str) -> str:
    pin = value.strip()
    if PIN.fullmatch(pin) is None:
        raise ValidationFailed("Use a 6-digit PIN", details={field: pin})
    return pin


def _currency(value: str) -> str:
    code = value.strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        raise ValidationFailed("Currency must be INR or USD", details={"currency": value})
    return code


def _minimum(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value < 0:
        raise ValidationFailed("Minimum freight cannot be negative", details={"minimumFreight": str(value)})
    if value == 0:
        return None
    return value


def _apply_minimum(amount: Decimal, minimum: Decimal | None) -> tuple[Decimal, bool]:
    if minimum is not None and amount < minimum:
        return _money(minimum), True
    return _money(amount), False


def organisation_for(session: Session, actor: Actor) -> Organisation:
    actor.require(NegotiationPermission.SUPPLY)
    user = session.get(User, actor.user_id)
    if user is None or user.organisation is None:
        raise ValidationFailed("Only a supplier can set freight")
    return user.organisation


def lanes(session: Session, organisation_id: uuid.UUID) -> list[SupplierFreightLane]:
    return list(session.scalars(
        select(SupplierFreightLane)
        .where(SupplierFreightLane.organisation_id == organisation_id)
        .order_by(SupplierFreightLane.destination_pin, SupplierFreightLane.currency)
    ))


def km_rate(session: Session, organisation_id: uuid.UUID, currency: str = "INR") -> SupplierFreightKmRate | None:
    return session.scalar(select(SupplierFreightKmRate).where(
        SupplierFreightKmRate.organisation_id == organisation_id,
        SupplierFreightKmRate.currency == currency,
    ))


def set_dispatch(session: Session, actor: Actor, *, pin: str, label: str) -> Organisation:
    org = organisation_for(session, actor)
    text = label.strip()
    if not text or len(text) > 64:
        raise ValidationFailed("Dispatch place is required", details={"field": "dispatchLabel"})
    org.dispatch_pin = _pin(pin, "dispatchPin")
    org.dispatch_label = text
    session.flush()
    return org


def save_lane(
    session: Session,
    actor: Actor,
    *,
    destination_pin: str,
    destination_label: str,
    rate_per_kg: Decimal,
    currency: str,
    minimum_freight: Decimal | None = None,
    is_active: bool = True,
    lane_id: uuid.UUID | None = None,
) -> SupplierFreightLane:
    org = organisation_for(session, actor)
    if not org.dispatch_pin:
        raise ValidationFailed("Set your dispatch PIN before saving a lane", details={"field": "dispatchPin"})
    label = destination_label.strip()
    if not label or len(label) > 64:
        raise ValidationFailed("Destination place is required", details={"field": "destinationLabel"})
    if rate_per_kg <= 0:
        raise ValidationFailed("Freight rate must be greater than zero", details={"ratePerKg": str(rate_per_kg)})
    code = _currency(currency)
    destination = _pin(destination_pin, "destinationPin")
    minimum = _minimum(minimum_freight)
    if lane_id is None:
        row = session.scalar(select(SupplierFreightLane).where(
            SupplierFreightLane.organisation_id == org.id,
            SupplierFreightLane.origin_pin == org.dispatch_pin,
            SupplierFreightLane.destination_pin == destination,
            SupplierFreightLane.currency == code,
        ))
        if row is None:
            row = SupplierFreightLane(
                organisation_id=org.id,
                origin_pin=org.dispatch_pin,
                destination_pin=destination,
                destination_label=label,
                rate_per_kg=rate_per_kg,
                currency=code,
            )
            session.add(row)
    else:
        row = session.get(SupplierFreightLane, lane_id)
        if row is None or row.organisation_id != org.id:
            raise NotFound("Freight lane not found", details={"laneId": str(lane_id)})
        row.destination_pin = destination
        row.origin_pin = org.dispatch_pin
    row.destination_label = label
    row.rate_per_kg = rate_per_kg
    row.currency = code
    row.minimum_freight = minimum
    row.is_active = is_active
    session.flush()
    return row


def remove_lane(session: Session, actor: Actor, lane_id: uuid.UUID) -> None:
    org = organisation_for(session, actor)
    row = session.get(SupplierFreightLane, lane_id)
    if row is None or row.organisation_id != org.id:
        raise NotFound("Freight lane not found", details={"laneId": str(lane_id)})
    session.delete(row)
    session.flush()


def save_km_rate(
    session: Session,
    actor: Actor,
    *,
    rate_per_km: Decimal,
    currency: str,
    minimum_freight: Decimal | None = None,
    is_active: bool = True,
) -> SupplierFreightKmRate:
    org = organisation_for(session, actor)
    if rate_per_km <= 0:
        raise ValidationFailed("Distance rate must be greater than zero", details={"ratePerKm": str(rate_per_km)})
    code = _currency(currency)
    row = km_rate(session, org.id, code)
    if row is None:
        row = SupplierFreightKmRate(organisation_id=org.id, currency=code, rate_per_km=rate_per_km)
        session.add(row)
    row.rate_per_km = rate_per_km
    row.minimum_freight = _minimum(minimum_freight)
    row.is_active = is_active
    session.flush()
    return row


def quote(
    session: Session,
    organisation: Organisation,
    currency: str,
    destination_pin: str,
    quantity: Decimal,
) -> dict | None:
    """This supplier's freight for one destination. None when they have not set a rate that applies."""
    origin = organisation.dispatch_pin
    if not origin or quantity <= 0:
        return None
    lane = session.scalar(select(SupplierFreightLane).where(
        SupplierFreightLane.organisation_id == organisation.id,
        SupplierFreightLane.origin_pin == origin,
        SupplierFreightLane.destination_pin == destination_pin,
        SupplierFreightLane.currency == currency,
        SupplierFreightLane.is_active.is_(True),
    ))
    if lane is not None:
        amount, applied = _apply_minimum(_money(lane.rate_per_kg * quantity), lane.minimum_freight)
        return {"basis": "lane", "freight": amount, "minimum_applied": applied, "label": lane.destination_label or "Saved lane"}
    rate = km_rate(session, organisation.id, currency)
    if rate is None or not rate.is_active:
        return None
    found = road_distance(session, origin, destination_pin, get_distance_provider())
    if found is None:
        return None
    kilometres, _source = found
    amount, applied = _apply_minimum(_money(kilometres * rate.rate_per_km), rate.minimum_freight)
    return {"basis": "per_km", "freight": amount, "minimum_applied": applied, "label": "Rate per km"}
