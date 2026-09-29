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
from app.freight.constants import ESTIMATE_NOTE, RATE_UNIT, FreightPermission
from app.identity.service import Actor
from app.models.freight import FreightRule
from app.models.identity import User

PIN = re.compile(r"^[1-9][0-9]{5}$")
MONEY = Decimal("0.0001")


def _pin(value: str, field: str) -> str:
    pin = value.strip()
    if PIN.fullmatch(pin) is None:
        raise ValidationFailed("PIN must be a 6-digit Indian PIN", details={field: value})
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
    origin_pin = _pin(fields["origin_pin"], "originPin")
    destination_pin = _pin(fields["destination_pin"], "destinationPin")
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


def matching_rule(
    session: Session, *, origin_pin: str, destination_pin: str, currency: str, on: date | None = None,
) -> FreightRule | None:
    day = on or business_today()
    return session.scalars(
        select(FreightRule)
        .where(
            FreightRule.is_active.is_(True),
            FreightRule.origin_pin == origin_pin,
            FreightRule.destination_pin == destination_pin,
            FreightRule.currency == currency,
            FreightRule.effective_from <= day,
            or_(FreightRule.effective_to.is_(None), FreightRule.effective_to >= day),
        )
        .order_by(FreightRule.effective_from.desc(), FreightRule.created_at.desc())
    ).first()


def estimate(
    session: Session,
    *,
    supplier_user_id: uuid.UUID,
    product_code: str,
    quantity: Decimal,
    destination_pin: str,
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
    material = _money(listing.asking_price * quantity)
    freight = None
    applied_minimum = False
    if rule is not None:
        freight = _money(rule.rate_per_kg * quantity)
        if rule.minimum_freight is not None and freight < rule.minimum_freight:
            freight = _money(rule.minimum_freight)
            applied_minimum = True
    landed = _money(material + freight) if freight is not None else None
    per_unit = _money(landed / quantity) if landed is not None else None
    return {
        "listing": listing,
        "supplier": supplier,
        "origin_pin": origin,
        "origin_label": supplier.organisation.dispatch_label if supplier and supplier.organisation else None,
        "destination_pin": pin,
        "destination_label": rule.destination_label if rule else None,
        "quantity": quantity,
        "material": material,
        "freight": freight,
        "minimum_applied": applied_minimum,
        "landed": landed,
        "per_unit": per_unit,
        "rule": rule,
        "note": ESTIMATE_NOTE,
    }
