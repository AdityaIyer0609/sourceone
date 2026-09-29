"""Supplier listings. Asking prices never become benchmarks and are never read from the ERP."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.catalogue import products as catalogue
from app.core.errors import NotFound, ValidationFailed
from app.identity.service import Actor, get_user_permissions
from app.models.catalogue import Product
from app.models.identity import User
from app.models.listing import AVAILABILITY, SupplierListing
from app.negotiation.constants import NegotiationPermission
from app.pricing.constants import SUPPORTED_CURRENCIES


def create_listing(
    session: Session,
    actor: Actor,
    *,
    product_code: str,
    minimum_quantity: Decimal,
    asking_price: Decimal,
    currency: str,
    availability: str,
    is_active: bool = True,
) -> SupplierListing:
    actor.require(NegotiationPermission.SUPPLY)
    if availability not in AVAILABILITY:
        raise ValidationFailed("Availability must be in_stock, limited or on_request", details={"availability": availability})
    code = currency.upper()
    if code not in SUPPORTED_CURRENCIES:
        raise ValidationFailed("Currency must be INR or USD", details={"currency": currency})
    product = catalogue.get_active_product(session, product_code)
    existing = session.scalar(
        select(SupplierListing).where(
            SupplierListing.supplier_user_id == actor.user_id, SupplierListing.product_id == product.id
        )
    )
    if existing is not None:
        raise ValidationFailed("This supplier already has a listing for this product", details={"listingId": str(existing.id)})
    listing = SupplierListing(
        supplier_user_id=actor.user_id,
        product_id=product.id,
        uom=product.uom,
        minimum_quantity=minimum_quantity,
        asking_price=asking_price,
        currency=code,
        is_active=is_active,
        availability=availability,
    )
    session.add(listing)
    session.flush()
    return listing


def set_listing_active(session: Session, actor: Actor, listing_id: uuid.UUID, *, is_active: bool) -> SupplierListing:
    actor.require(NegotiationPermission.SUPPLY)
    listing = session.get(SupplierListing, listing_id)
    if listing is None or listing.supplier_user_id != actor.user_id:
        raise NotFound("Listing not found", details={"listingId": str(listing_id)})
    listing.is_active = is_active
    session.flush()
    return listing


def can_supply(session: Session, user: User) -> bool:
    return user.is_active and not user.is_system and NegotiationPermission.SUPPLY in get_user_permissions(session, user.id)


def eligible_listings(session: Session, product: Product, *, currency: str | None = None) -> list[SupplierListing]:
    """Active listings from active suppliers. Currency, when given, must match the benchmark the buyer is viewing."""
    rows = session.scalars(
        select(SupplierListing)
        .where(SupplierListing.product_id == product.id, SupplierListing.is_active.is_(True))
        .options(selectinload(SupplierListing.supplier).selectinload(User.organisation))
        .order_by(SupplierListing.asking_price, SupplierListing.created_at)
    ).all()
    wanted = currency.upper() if currency else None
    return [
        row for row in rows
        if (wanted is None or row.currency == wanted) and can_supply(session, row.supplier)
    ]
