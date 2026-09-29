"""Admin item master for SourceOne products. Not the ERP item master."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_any
from app.api.v1 import pricing_presenters as present
from app.catalogue import listings as catalogue_listings
from app.catalogue import products as catalogue
from app.catalogue.specifications import specification_rows
from app.core.clock import utcnow
from app.identity.service import Actor
from app.models.catalogue import Product
from app.pricing import repository
from app.pricing.constants import PricingPermission
from app.schemas.catalogue import (
    AdminProductOut,
    ProductActiveIn,
    ProductEditIn,
    ProductIn,
    ProductSeriesOut,
    SeriesMapActiveIn,
    SeriesMapIn,
)
from app.schemas.pricing import SpecificationOut

router = APIRouter(prefix="/admin/products", tags=["item-master"])

Editor = Annotated[Actor, Depends(require_any(PricingPermission.EDIT, PricingPermission.CONFIGURE))]


def _present(products: list[Product], db: DbSession) -> list[AdminProductOut]:
    series_ids = {
        link.rate_series_id
        for product in products
        for link in product.series_links
        if link.is_active and link.rate_series.is_active
    }
    timelines = repository.timelines(db, series_ids)
    now = utcnow()
    out = []
    for product in products:
        series = []
        available = False
        for link in product.series_links:
            if link.is_active and link.rate_series.is_active:
                summary = present.benchmark_summary(link.rate_series, timelines.get(link.rate_series_id, []), now)
                availability = summary.availability
                available = available or availability == "available"
            else:
                availability = "rate_on_request"
            series.append(ProductSeriesOut(
                series_code=link.rate_series.code,
                display_name=link.rate_series.display_name,
                currency=link.rate_series.currency,
                display_order=link.display_order,
                is_active=link.is_active,
                availability=availability,
            ))
        out.append(AdminProductOut(
            product_code=product.product_code,
            name=product.name,
            category=product.category,
            subcategory=product.subcategory,
            description=product.description,
            uom=product.uom,
            is_active=product.is_active,
            benchmark_status="available" if available else "rate_on_request",
            listing_count=len(catalogue_listings.eligible_listings(db, product)),
            series=series,
            specifications=[SpecificationOut(**row) for row in specification_rows(product)],
        ))
    return out


def _one(db: DbSession, product: Product) -> AdminProductOut:
    return _present([catalogue.get_product(db, product.product_code)], db)[0]


@router.get("", response_model=list[AdminProductOut])
def list_products(
    db: DbSession,
    _: Editor,
    q: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    active: Annotated[bool | None, Query()] = None,
):
    return _present(list(catalogue.list_catalogue(db, search=q, category=category, active=active)), db)


@router.post("", response_model=AdminProductOut, status_code=201)
def create_product(body: ProductIn, db: DbSession, _: Editor):
    product = catalogue.create_product(
        db, product_code=body.product_code, name=body.name, category=body.category,
        subcategory=body.subcategory, description=body.description, uom=body.uom, is_active=body.is_active,
        specifications=body.specifications,
    )
    db.commit()
    return _one(db, product)


@router.patch("/{product_code}", response_model=AdminProductOut)
def update_product(product_code: str, body: ProductEditIn, db: DbSession, _: Editor):
    product = catalogue.update_product(
        db, product_code, name=body.name, category=body.category,
        subcategory=body.subcategory, description=body.description, specifications=body.specifications,
    )
    db.commit()
    return _one(db, product)


@router.post("/{product_code}/active", response_model=AdminProductOut)
def set_active(product_code: str, body: ProductActiveIn, db: DbSession, _: Editor):
    product = catalogue.set_product_active(db, product_code, is_active=body.is_active)
    db.commit()
    return _one(db, product)


@router.post("/{product_code}/series", response_model=AdminProductOut, status_code=201)
def map_series(product_code: str, body: SeriesMapIn, db: DbSession, _: Editor):
    product = catalogue.map_product_series(db, product_code, body.series_code, display_order=body.display_order)
    db.commit()
    return _one(db, product)


@router.post("/{product_code}/series/{series_code}/active", response_model=AdminProductOut)
def set_series_active(product_code: str, series_code: str, body: SeriesMapActiveIn, db: DbSession, _: Editor):
    product = catalogue.set_series_mapping_active(db, product_code, series_code, is_active=body.is_active)
    db.commit()
    return _one(db, product)


@router.delete("/{product_code}", status_code=409)
def delete_product(product_code: str, db: DbSession, _: Editor):
    catalogue.refuse_delete(db, product_code)
