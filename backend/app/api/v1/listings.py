"""Supplier listings and the buyers who can see them. Benchmarks are a different price."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, require_any
from app.api.v1.pricing_presenters import money
from app.catalogue import listings as service
from app.catalogue import products as catalogue
from app.core.errors import NotFound
from app.identity.service import Actor
from app.models.identity import User
from app.models.listing import SupplierListing
from app.negotiation.constants import NegotiationPermission
from app.pricing.constants import PricingPermission
from app.schemas.listing import ListingActiveIn, ListingIn, ListingOut

router = APIRouter(tags=["listings"])

Supplier = Annotated[Actor, Depends(require_any(NegotiationPermission.SUPPLY))]
Viewer = Annotated[Actor, Depends(require_any(PricingPermission.VIEW))]


def _out(listing: SupplierListing) -> ListingOut:
    return ListingOut(
        id=listing.id,
        product_code=listing.product.product_code,
        supplier_user_id=listing.supplier_user_id,
        supplier_name=listing.supplier.full_name,
        organisation=listing.supplier.organisation.name,
        origin_pin=listing.supplier.organisation.dispatch_pin,
        origin_label=listing.supplier.organisation.dispatch_label,
        uom=listing.uom,
        minimum_quantity=f"{listing.minimum_quantity.normalize():f}",
        asking_price=money(listing.asking_price, listing.currency),
        availability=listing.availability,
        is_active=listing.is_active,
    )


def _loaded(db: DbSession, listing_id: uuid.UUID) -> SupplierListing:
    listing = db.scalar(
        select(SupplierListing)
        .where(SupplierListing.id == listing_id)
        .options(
            selectinload(SupplierListing.product),
            selectinload(SupplierListing.supplier).selectinload(User.organisation),
        )
    )
    if listing is None:
        raise NotFound("Listing not found", details={"listingId": str(listing_id)})
    return listing


@router.post("/listings", response_model=ListingOut, status_code=201)
def create_listing(body: ListingIn, db: DbSession, actor: Supplier):
    listing = service.create_listing(
        db, actor, product_code=body.product_code, minimum_quantity=body.minimum_quantity,
        asking_price=body.asking_price, currency=body.currency, availability=body.availability,
        is_active=body.is_active,
    )
    db.commit()
    return _out(_loaded(db, listing.id))


@router.patch("/listings/{listing_id}", response_model=ListingOut)
def update_listing(listing_id: uuid.UUID, body: ListingActiveIn, db: DbSession, actor: Supplier):
    listing = service.set_listing_active(db, actor, listing_id, is_active=body.is_active)
    db.commit()
    return _out(_loaded(db, listing.id))


@router.get("/products/{product_code}/listings", response_model=list[ListingOut])
def list_product_listings(
    product_code: str,
    db: DbSession,
    _: Viewer,
    currency: Annotated[str | None, Query()] = None,
):
    product = catalogue.get_active_product(db, product_code)
    return [_out(listing) for listing in service.eligible_listings(db, product, currency=currency)]
