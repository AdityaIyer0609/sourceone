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


def resolve_maximum(availability: str, minimum: Decimal, maximum: Decimal | None) -> Decimal | None:
    """A limited listing must say how much the supplier can spare. Other listings have no cap."""
    if availability == "limited":
        if maximum is None or maximum <= 0:
            raise ValidationFailed(
                "A limited listing needs the quantity this supplier can spare",
                details={"field": "maximumQuantity"},
            )
        if maximum < minimum:
            raise ValidationFailed(
                "The available quantity must be at least the minimum",
                details={"field": "maximumQuantity"},
            )
        return maximum
    if maximum is not None:
        raise ValidationFailed("Only a limited listing has a maximum quantity", details={"field": "maximumQuantity"})
    return None


def supply_note(listing: SupplierListing, quantity: Decimal) -> str | None:
    """Information for the buyer. It does not change the quantity they can request or order."""
    if listing.availability == "on_request":
        return "This supplier has not confirmed the material is ready. Ask them, and place an order only after they accept."
    if listing.maximum_quantity is not None and quantity > listing.maximum_quantity:
        cap = f"{listing.maximum_quantity.normalize():f}"
        return f"This quantity is above the {cap} {listing.uom} this supplier said they can spare."
    return None


def insert_listing(
    session: Session,
    *,
    supplier_user_id: uuid.UUID,
    product: Product,
    minimum_quantity: Decimal,
    asking_price: Decimal,
    currency: str,
    availability: str,
    is_active: bool = True,
    maximum_quantity: Decimal | None = None,
) -> SupplierListing:
    if availability not in AVAILABILITY:
        raise ValidationFailed("Availability must be in_stock, limited or on_request", details={"availability": availability})
    cap = resolve_maximum(availability, minimum_quantity, maximum_quantity)
    code = currency.upper()
    if code not in SUPPORTED_CURRENCIES:
        raise ValidationFailed("Currency must be INR or USD", details={"currency": currency})
    existing = session.scalar(
        select(SupplierListing).where(
            SupplierListing.supplier_user_id == supplier_user_id, SupplierListing.product_id == product.id
        )
    )
    if existing is not None:
        raise ValidationFailed("This supplier already has a listing for this product", details={"listingId": str(existing.id)})
    listing = SupplierListing(
        supplier_user_id=supplier_user_id,
        product_id=product.id,
        uom=product.uom,
        minimum_quantity=minimum_quantity,
        maximum_quantity=cap,
        asking_price=asking_price,
        currency=code,
        is_active=is_active,
        availability=availability,
    )
    session.add(listing)
    session.flush()
    from app.catalogue import market_average

    market_average.record(session, product.id, code)
    return listing


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
    maximum_quantity: Decimal | None = None,
) -> SupplierListing:
    actor.require(NegotiationPermission.SUPPLY)
    product = catalogue.get_active_product(session, product_code)
    return insert_listing(
        session, supplier_user_id=actor.user_id, product=product, minimum_quantity=minimum_quantity,
        asking_price=asking_price, currency=currency, availability=availability, is_active=is_active,
        maximum_quantity=maximum_quantity,
    )


def _own(session: Session, actor: Actor, listing_id: uuid.UUID) -> SupplierListing:
    actor.require(NegotiationPermission.SUPPLY)
    listing = session.get(SupplierListing, listing_id)
    if listing is None or listing.supplier_user_id != actor.user_id:
        raise NotFound("Listing not found", details={"listingId": str(listing_id)})
    return listing


def own_listings(session: Session, actor: Actor) -> list[SupplierListing]:
    """Every listing this supplier owns, including inactive ones. Not the public catalogue."""
    actor.require(NegotiationPermission.SUPPLY)
    return list(session.scalars(
        select(SupplierListing)
        .where(SupplierListing.supplier_user_id == actor.user_id)
        .options(
            selectinload(SupplierListing.product),
            selectinload(SupplierListing.supplier).selectinload(User.organisation),
        )
        .order_by(SupplierListing.created_at.desc())
    ).all())


def update_listing(
    session: Session,
    actor: Actor,
    listing_id: uuid.UUID,
    *,
    is_active: bool | None = None,
    asking_price: Decimal | None = None,
    minimum_quantity: Decimal | None = None,
    availability: str | None = None,
    maximum_quantity: Decimal | None = None,
    maximum_set: bool = False,
) -> SupplierListing:
    if is_active is None and asking_price is None and minimum_quantity is None and availability is None and not maximum_set:
        raise ValidationFailed("Choose a listing field to update")
    listing = _own(session, actor, listing_id)
    next_availability = availability if availability is not None else listing.availability
    if availability is not None and next_availability not in AVAILABILITY:
        raise ValidationFailed("Availability must be in_stock, limited or on_request", details={"availability": availability})
    next_minimum = minimum_quantity if minimum_quantity is not None else listing.minimum_quantity
    cap = listing.maximum_quantity
    if maximum_set or availability is not None or minimum_quantity is not None:
        chosen = maximum_quantity if maximum_set else listing.maximum_quantity
        if next_availability != "limited":
            if maximum_set and maximum_quantity is not None:
                raise ValidationFailed("Only a limited listing has a maximum quantity", details={"field": "maximumQuantity"})
            chosen = None
        cap = resolve_maximum(next_availability, next_minimum, chosen)
    market_changed = False
    if asking_price is not None and asking_price != listing.asking_price:
        listing.asking_price = asking_price
        market_changed = True
    if minimum_quantity is not None:
        listing.minimum_quantity = minimum_quantity
    if availability is not None:
        listing.availability = availability
    if maximum_set or availability is not None or minimum_quantity is not None:
        listing.maximum_quantity = cap
    if is_active is not None and is_active != listing.is_active:
        listing.is_active = is_active
        market_changed = True
    session.flush()
    if market_changed:
        from app.catalogue import market_average
        market_average.record(session, listing.product_id, listing.currency)
    return listing


def set_listing_active(session: Session, actor: Actor, listing_id: uuid.UUID, *, is_active: bool) -> SupplierListing:
    return update_listing(session, actor, listing_id, is_active=is_active)


def can_supply(session: Session, user: User) -> bool:
    return user.is_active and not user.is_system and NegotiationPermission.SUPPLY in get_user_permissions(session, user.id)


def eligible_listings(session: Session, product: Product, *, currency: str | None = None) -> list[SupplierListing]:
    """Active listings from active suppliers. Currency, when given, must match the benchmark the buyer is viewing."""
    rows = session.scalars(
        select(SupplierListing)
        .where(SupplierListing.product_id == product.id, SupplierListing.is_active.is_(True))
        .options(
            selectinload(SupplierListing.product),
            selectinload(SupplierListing.supplier).selectinload(User.organisation),
        )
        .order_by(SupplierListing.asking_price, SupplierListing.created_at)
    ).all()
    wanted = currency.upper() if currency else None
    return [
        row for row in rows
        if (wanted is None or row.currency == wanted) and can_supply(session, row.supplier)
    ]
