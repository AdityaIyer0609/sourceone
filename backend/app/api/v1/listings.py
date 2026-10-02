"""Supplier listings and the buyers who can see them. Benchmarks are a different price."""

import uuid
from decimal import Decimal
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
from app.schemas.supplier import SupplierMatchListOut
from app.suppliers.matching import match_suppliers

router = APIRouter(tags=["listings"])

Supplier = Annotated[Actor, Depends(require_any(NegotiationPermission.SUPPLY))]
Viewer = Annotated[Actor, Depends(require_any(PricingPermission.VIEW))]


def _out(listing: SupplierListing) -> ListingOut:
    return ListingOut(
        id=listing.id,
        product_code=listing.product.product_code,
        product_name=listing.product.name,
        supplier_user_id=listing.supplier_user_id,
        supplier_name=listing.supplier.full_name,
        organisation=listing.supplier.organisation.name,
        organisation_id=listing.supplier.organisation_id,
        origin_pin=listing.supplier.organisation.dispatch_pin,
        origin_label=listing.supplier.organisation.dispatch_label,
        uom=listing.uom,
        minimum_quantity=f"{listing.minimum_quantity.normalize():f}",
        maximum_quantity=f"{listing.maximum_quantity.normalize():f}" if listing.maximum_quantity is not None else None,
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
        is_active=body.is_active, maximum_quantity=body.maximum_quantity,
    )
    db.commit()
    return _out(_loaded(db, listing.id))


@router.get("/listings", response_model=list[ListingOut])
def list_own_listings(db: DbSession, actor: Supplier):
    return [_out(listing) for listing in service.own_listings(db, actor)]


@router.patch("/listings/{listing_id}", response_model=ListingOut)
def update_listing(listing_id: uuid.UUID, body: ListingActiveIn, db: DbSession, actor: Supplier):
    listing = service.update_listing(
        db, actor, listing_id, is_active=body.is_active, asking_price=body.asking_price,
        minimum_quantity=body.minimum_quantity, availability=body.availability,
        maximum_quantity=body.maximum_quantity, maximum_set="maximum_quantity" in body.model_fields_set,
    )
    db.commit()
    return _out(_loaded(db, listing.id))


@router.get("/products/{product_code}/supplier-matches", response_model=SupplierMatchListOut)
def match_product_suppliers(
    product_code: str,
    db: DbSession,
    actor: Viewer,
    quantity: Annotated[Decimal, Query(gt=0)],
    uom: Annotated[str, Query(min_length=1)],
    destination_pin: Annotated[str, Query(alias="destinationPin", min_length=6, max_length=6)],
    currency: Annotated[str | None, Query()] = None,
):
    from app.identity.privacy import suppliers_hidden
    if suppliers_hidden(actor):
        return SupplierMatchListOut(
            product_code=product_code, quantity=f"{quantity.normalize():f}", uom=uom,
            destination_pin=destination_pin, matches=[],
        )
    return match_suppliers(
        db, product_code=product_code, quantity=quantity, uom=uom,
        destination_pin=destination_pin, currency=currency,
    )


@router.get("/products/{product_code}/listings", response_model=list[ListingOut])
def list_product_listings(
    product_code: str,
    db: DbSession,
    actor: Viewer,
    currency: Annotated[str | None, Query()] = None,
):
    from app.identity.privacy import suppliers_hidden
    product = catalogue.get_active_product(db, product_code)
    rows = service.eligible_listings(db, product, currency=currency)
    if suppliers_hidden(actor):
        rows = [listing for listing in rows if listing.supplier_user_id == actor.user_id]
    return [_out(listing) for listing in rows]
