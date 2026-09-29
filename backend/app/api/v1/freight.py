"""SourceOne freight rules and buyer estimates. Estimates are not stored and never become a price."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.api.v1.pricing_presenters import money
from app.freight import service
from app.freight.constants import FreightPermission
from app.identity.service import Actor
from app.models.freight import FreightRule
from app.pricing.constants import PricingPermission
from app.schemas.freight import FreightEstimateIn, FreightEstimateOut, FreightRuleIn, FreightRuleOut

router = APIRouter(tags=["freight"])

Manager = Annotated[Actor, Depends(require_any(FreightPermission.MANAGE))]
Viewer = Annotated[Actor, Depends(require_any(PricingPermission.VIEW))]


def _amount(value) -> str | None:
    return None if value is None else f"{value:.4f}"


def _rule(rule: FreightRule) -> FreightRuleOut:
    return FreightRuleOut(
        id=rule.id,
        origin_pin=rule.origin_pin,
        origin_label=rule.origin_label,
        destination_pin=rule.destination_pin,
        destination_label=rule.destination_label,
        rate_per_kg=f"{rule.rate_per_kg:.4f}",
        rate_unit="KG",
        currency=rule.currency,
        minimum_freight=_amount(rule.minimum_freight),
        is_active=rule.is_active,
        effective_from=rule.effective_from,
        effective_to=rule.effective_to,
    )


def _fields(body: FreightRuleIn) -> dict:
    return body.model_dump()


@router.get("/admin/freight/rules", response_model=list[FreightRuleOut])
def list_rules(db: DbSession, _: Manager):
    return [_rule(rule) for rule in service.list_rules(db)]


@router.post("/admin/freight/rules", response_model=FreightRuleOut, status_code=201)
def create_rule(body: FreightRuleIn, db: DbSession, actor: Manager):
    rule = service.create_rule(db, actor, **_fields(body))
    db.commit()
    return _rule(rule)


@router.patch("/admin/freight/rules/{rule_id}", response_model=FreightRuleOut)
def update_rule(rule_id: uuid.UUID, body: FreightRuleIn, db: DbSession, actor: Manager):
    rule = service.update_rule(db, actor, rule_id, **_fields(body))
    db.commit()
    return _rule(rule)


@router.post("/freight/estimates", response_model=FreightEstimateOut)
def estimate(body: FreightEstimateIn, db: DbSession, _: Viewer):
    result = service.estimate(
        db, supplier_user_id=body.supplier_user_id, product_code=body.product_code,
        quantity=body.quantity, destination_pin=body.destination_pin,
    )
    listing = result["listing"]
    status = "estimated" if result["freight"] is not None else "on_request"
    return FreightEstimateOut(
        supplier_user_id=listing.supplier_user_id,
        product_code=listing.product.product_code,
        quantity=f"{result['quantity'].normalize():f}",
        uom=listing.uom,
        origin_pin=result["origin_pin"],
        origin_label=result["origin_label"],
        destination_pin=result["destination_pin"],
        destination_label=result["destination_label"],
        supplier_asking_price=money(listing.asking_price, listing.currency),
        material_value=money(result["material"], listing.currency),
        freight_status=status,
        freight=money(result["freight"], listing.currency) if result["freight"] is not None else None,
        minimum_freight_applied=result["minimum_applied"],
        landed_cost_per_unit=money(result["per_unit"], listing.currency) if result["per_unit"] is not None else None,
        landed_value=money(result["landed"], listing.currency) if result["landed"] is not None else None,
        rule_id=result["rule"].id if result["rule"] else None,
        note=result["note"],
    )
