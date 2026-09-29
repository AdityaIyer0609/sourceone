"""Freight estimates. A match is an active SourceOne rule for the supplier origin, destination PIN and currency."""

import re
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.catalogue import listings as catalogue_listings
from app.catalogue import products as catalogue
from app.core.clock import business_today
from app.core.errors import NotFound, ValidationFailed
from app.freight.constants import (
    DEFAULT_NOTE,
    DEFAULT_RATE_PER_KM,
    DISTANCE_NOTE,
    ESTIMATE_NOTE,
    RATE_UNIT,
    FreightPermission,
)
from app.freight.distance import DistanceProvider, get_distance_provider, road_distance
from app.identity.service import Actor
from app.models.freight import FreightDefault, FreightDistanceRate, FreightRule
from app.models.identity import User

PIN = re.compile(r"^[1-9][0-9]{5}$")
ZONE = re.compile(r"^[1-9][0-9]{2}(?:[0-9]{3})?$")
MONEY = Decimal("0.0001")


def _pin(value: str, field: str) -> str:
    pin = value.strip()
    if PIN.fullmatch(pin) is None:
        raise ValidationFailed("PIN must be a 6-digit Indian PIN", details={field: value})
    return pin


def _zone(value: str, field: str) -> str:
    pin = value.strip()
    if ZONE.fullmatch(pin) is None:
        raise ValidationFailed("Use a 6-digit PIN or a 3-digit PIN zone", details={field: value})
    return pin


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _currency(value: str) -> str:
    code = value.strip().upper()
    if code not in ("INR", "USD"):
        raise ValidationFailed("Currency must be INR or USD", details={"currency": value})
    return code


def create_rule(session: Session, actor: Actor, **fields) -> FreightRule:
    actor.require(FreightPermission.MANAGE)
    rule = FreightRule(**_clean(fields))
    session.add(rule)
    session.flush()
    return rule


def update_rule(session: Session, actor: Actor, rule_id: uuid.UUID, **fields) -> FreightRule:
    actor.require(FreightPermission.MANAGE)
    rule = session.get(FreightRule, rule_id)
    if rule is None:
        raise NotFound("Freight rule not found", details={"ruleId": str(rule_id)})
    for key, value in _clean(fields).items():
        setattr(rule, key, value)
    session.flush()
    return rule


def list_rules(session: Session) -> list[FreightRule]:
    return list(session.scalars(
        select(FreightRule).order_by(FreightRule.origin_pin, FreightRule.destination_pin, FreightRule.effective_from.desc())
    ).all())


def _clean(fields: dict) -> dict:
    origin_pin = _zone(fields["origin_pin"], "originPin")
    destination_pin = _zone(fields["destination_pin"], "destinationPin")
    currency = _currency(fields["currency"])
    rate = Decimal(fields["rate_per_kg"])
    if rate <= 0:
        raise ValidationFailed("Freight rate must be greater than zero", details={"ratePerKg": str(rate)})
    minimum = fields.get("minimum_freight")
    if minimum is not None:
        minimum = Decimal(minimum)
        if minimum < 0:
            raise ValidationFailed("Minimum freight cannot be negative", details={"minimumFreight": str(minimum)})
        if minimum == 0:
            minimum = None
    effective_from = fields["effective_from"]
    effective_to = fields.get("effective_to")
    if effective_to is not None and effective_to < effective_from:
        raise ValidationFailed("Effective to must be on or after effective from")
    return {
        "origin_pin": origin_pin,
        "origin_label": fields["origin_label"].strip(),
        "destination_pin": destination_pin,
        "destination_label": fields["destination_label"].strip(),
        "rate_per_kg": rate,
        "rate_unit": RATE_UNIT,
        "currency": currency,
        "minimum_freight": minimum,
        "is_active": fields.get("is_active", True),
        "effective_from": effective_from,
        "effective_to": effective_to,
    }


def _cover(rule_pin: str, actual: str) -> int:
    if rule_pin == actual:
        return 2
    if len(rule_pin) == 3 and actual.startswith(rule_pin):
        return 1
    return 0


def matching_rule(
    session: Session, *, origin_pin: str, destination_pin: str, currency: str, on: date | None = None,
) -> FreightRule | None:
    day = on or business_today()
    rules = session.scalars(
        select(FreightRule)
        .where(
            FreightRule.is_active.is_(True),
            FreightRule.currency == currency,
            FreightRule.effective_from <= day,
            or_(FreightRule.effective_to.is_(None), FreightRule.effective_to >= day),
        )
    ).all()
    ranked = []
    for rule in rules:
        origin_score = _cover(rule.origin_pin, origin_pin)
        destination_score = _cover(rule.destination_pin, destination_pin)
        if origin_score and destination_score:
            ranked.append((origin_score + destination_score, rule.effective_from, rule.created_at, rule))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return ranked[0][3]


def active_default(session: Session, currency: str) -> FreightDefault | None:
    row = session.scalar(select(FreightDefault).where(FreightDefault.currency == currency))
    return row if row is not None and row.is_active else None


def list_defaults(session: Session) -> list[FreightDefault]:
    return list(session.scalars(select(FreightDefault).order_by(FreightDefault.currency)).all())


def save_default(session: Session, actor: Actor, **fields) -> FreightDefault:
    actor.require(FreightPermission.MANAGE)
    currency = _currency(fields["currency"])
    rate = Decimal(fields["rate_per_kg"])
    if rate <= 0:
        raise ValidationFailed("Freight rate must be greater than zero", details={"ratePerKg": str(rate)})
    minimum = fields.get("minimum_freight")
    if minimum is not None:
        minimum = Decimal(minimum)
        if minimum < 0:
            raise ValidationFailed("Minimum freight cannot be negative", details={"minimumFreight": str(minimum)})
        if minimum == 0:
            minimum = None
    row = session.scalar(select(FreightDefault).where(FreightDefault.currency == currency))
    if row is None:
        row = FreightDefault(currency=currency, rate_per_kg=rate)
        session.add(row)
    row.rate_per_kg = rate
    row.minimum_freight = minimum
    row.is_active = fields.get("is_active", True)
    session.flush()
    return row


def active_distance_rate(session: Session, currency: str) -> FreightDistanceRate | None:
    row = session.scalar(select(FreightDistanceRate).where(FreightDistanceRate.currency == currency))
    return row if row is not None and row.is_active else None


def list_distance_rates(session: Session) -> list[FreightDistanceRate]:
    return list(session.scalars(select(FreightDistanceRate).order_by(FreightDistanceRate.currency)).all())


def save_distance_rate(session: Session, actor: Actor, **fields) -> FreightDistanceRate:
    actor.require(FreightPermission.MANAGE)
    currency = _currency(fields["currency"])
    rate = Decimal(fields["rate_per_km"])
    if rate <= 0:
        raise ValidationFailed("Distance rate must be greater than zero", details={"ratePerKm": str(rate)})
    minimum = fields.get("minimum_freight")
    if minimum is not None:
        minimum = Decimal(minimum)
        if minimum < 0:
            raise ValidationFailed("Minimum freight cannot be negative", details={"minimumFreight": str(minimum)})
        if minimum == 0:
            minimum = None
    row = session.scalar(select(FreightDistanceRate).where(FreightDistanceRate.currency == currency))
    if row is None:
        row = FreightDistanceRate(currency=currency, rate_per_km=rate)
        session.add(row)
    row.rate_per_km = rate
    row.minimum_freight = minimum
    row.is_active = fields.get("is_active", True)
    session.flush()
    return row


def estimate(
    session: Session,
    *,
    supplier_user_id: uuid.UUID,
    product_code: str,
    quantity: Decimal,
    destination_pin: str,
    include_distance: bool = False,
    distance_provider: DistanceProvider | None = None,
) -> dict:
    if quantity <= 0:
        raise ValidationFailed("Quantity must be greater than zero", details={"quantity": str(quantity)})
    pin = _pin(destination_pin, "destinationPin")
    product = catalogue.get_active_product(session, product_code)
    listing = next(
        (row for row in catalogue_listings.eligible_listings(session, product) if row.supplier_user_id == supplier_user_id),
        None,
    )
    if listing is None:
        raise NotFound("No active listing from this supplier", details={"supplierUserId": str(supplier_user_id)})
    supplier = session.get(User, supplier_user_id)
    origin = supplier.organisation.dispatch_pin if supplier and supplier.organisation else None
    rule = matching_rule(
        session, origin_pin=origin, destination_pin=pin, currency=listing.currency,
    ) if origin else None
    default = None if rule is not None else active_default(session, listing.currency)
    material = _money(listing.asking_price * quantity)
    freight = None
    applied_minimum = False
    if rule is not None:
        freight = _money(rule.rate_per_kg * quantity)
        minimum = rule.minimum_freight
    elif default is not None:
        freight = _money(default.rate_per_kg * quantity)
        minimum = default.minimum_freight
    else:
        minimum = None
    if freight is not None and minimum is not None and freight < minimum:
        freight = _money(minimum)
        applied_minimum = True
    match = None
    note = ESTIMATE_NOTE
    label = None
    if rule is not None:
        match = "lane" if len(rule.origin_pin) == 6 and len(rule.destination_pin) == 6 else "zone"
        label = rule.destination_label
    elif default is not None:
        match = "default"
        note = DEFAULT_NOTE
        label = "Default rate"
    landed = _money(material + freight) if freight is not None else None
    per_unit = _money(landed / quantity) if landed is not None else None
    distance = _distance_quote(
        session, origin=origin, destination=pin, currency=listing.currency,
        material=material, quantity=quantity, include=include_distance,
        provider=distance_provider or get_distance_provider(),
    )
    return {
        "listing": listing,
        "supplier": supplier,
        "origin_pin": origin,
        "origin_label": supplier.organisation.dispatch_label if supplier and supplier.organisation else None,
        "destination_pin": pin,
        "destination_label": label,
        "quantity": quantity,
        "material": material,
        "freight": freight,
        "minimum_applied": applied_minimum,
        "landed": landed,
        "per_unit": per_unit,
        "rule": rule,
        "match": match,
        "note": note,
        **distance,
    }


def _distance_quote(
    session: Session, *, origin: str | None, destination: str, currency: str,
    material: Decimal, quantity: Decimal, include: bool, provider: DistanceProvider,
) -> dict:
    empty = {
        "distance_status": "not_requested",
        "distance_freight": None,
        "distance_minimum_applied": False,
        "distance_landed": None,
        "distance_per_unit": None,
        "distance_rate_per_km": None,
        "road_km": None,
        "distance_source": None,
        "distance_note": None,
    }
    if not include:
        return empty
    rate_row = active_distance_rate(session, currency) if origin else None
    rate = rate_row.rate_per_km if rate_row is not None else DEFAULT_RATE_PER_KM
    minimum = rate_row.minimum_freight if rate_row is not None else None
    if not origin:
        return {**empty, "distance_status": "on_request", "distance_rate_per_km": rate, "distance_note": DISTANCE_NOTE}
    found = road_distance(session, origin, destination, provider)
    if found is None:
        return {**empty, "distance_status": "on_request", "distance_rate_per_km": rate, "distance_note": DISTANCE_NOTE}
    kilometres, source = found
    freight = _money(kilometres * rate)
    applied = False
    if minimum is not None and freight < minimum:
        freight = _money(minimum)
        applied = True
    landed = _money(material + freight)
    return {
        "distance_status": "estimated",
        "distance_freight": freight,
        "distance_minimum_applied": applied,
        "distance_landed": landed,
        "distance_per_unit": _money(landed / quantity),
        "distance_rate_per_km": rate,
        "road_km": kilometres,
        "distance_source": source,
        "distance_note": DISTANCE_NOTE,
    }
