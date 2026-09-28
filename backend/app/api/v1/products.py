"""Buyer-facing product catalogue (signed-in users with pricing.view)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.api.v1 import pricing_presenters as present
from app.catalogue import products as catalogue
from app.core.clock import utcnow
from app.identity.service import Actor
from app.models.catalogue import Product
from app.pricing import repository
from app.pricing.constants import UNIT_LABELS, PricingPermission, label_for
from app.schemas import pricing as schemas

router = APIRouter(prefix="/products", tags=["products"])

Viewer = Annotated[Actor, Depends(require_any(PricingPermission.VIEW))]


def _present(products: list[Product], db: DbSession) -> list[schemas.ProductOut]:
    series_by_product = {p.id: catalogue.buyer_series(p) for p in products}
    timelines = repository.timelines(db, {s.id for series in series_by_product.values() for s in series})
    now = utcnow()
    out = []
    for product in products:
        pricing = [
            present.benchmark_summary(s, timelines.get(s.id, []), now) for s in series_by_product[product.id]
        ]
        default = pricing[0] if pricing else None
        out.append(schemas.ProductOut(
            product_code=product.product_code,
            name=product.name,
            category=product.category,
            subcategory=product.subcategory,
            description=product.description,
            uom=schemas.CodeLabel(code=product.uom, label=label_for(UNIT_LABELS, product.uom)),
            availability=default.availability if default else "rate_on_request",
            default_series_code=default.series_code if default else None,
            pricing=pricing,
        ))
    return out


@router.get("", response_model=list[schemas.ProductOut])
def list_products(db: DbSession, _: Viewer, category: str | None = None):
    return _present(list(catalogue.list_active_products(db, category=category)), db)


@router.get("/{product_code}", response_model=schemas.ProductOut)
def get_product(product_code: str, db: DbSession, _: Viewer):
    return _present([catalogue.get_active_product(db, product_code)], db)[0]
