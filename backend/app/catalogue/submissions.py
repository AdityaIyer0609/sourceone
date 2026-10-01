"""Supplier requests for a new catalogue product. Acceptance creates the product and that supplier's listing."""

import re
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.catalogue import listings as catalogue_listings
from app.catalogue import products as catalogue
from app.catalogue.specifications import require_core_specifications
from app.core.clock import utcnow
from app.core.errors import InvalidStateTransition, NotFound, ValidationFailed
from app.identity.service import Actor
from app.models.catalogue import ProductSubmission
from app.models.identity import User
from app.models.listing import AVAILABILITY
from app.negotiation.constants import NegotiationPermission
from app.pricing.constants import SUPPORTED_CURRENCIES, PricingPermission

CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,63}$")
STATUSES = ("pending", "accepted", "rejected")


def _code(value: str) -> str:
    code = value.strip().upper()
    if CODE.fullmatch(code) is None:
        raise ValidationFailed(
            "Product code must start with a letter or number and use only letters, numbers, hyphens, or underscores",
            details={"productCode": value},
        )
    return code


def _text(value: str, field: str, limit: int) -> str:
    text = value.strip()
    if not text or len(text) > limit:
        raise ValidationFailed("This field is required", details={"field": field})
    return text


def _optional(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > limit:
        raise ValidationFailed("This field is too long", details={"limit": limit})
    return text


def submit(
    session: Session,
    actor: Actor,
    *,
    proposed_code: str,
    name: str,
    category: str,
    uom: str,
    specifications: dict | None,
    asking_price: Decimal,
    currency: str,
    minimum_quantity: Decimal,
    availability: str,
    maximum_quantity: Decimal | None = None,
    subcategory: str | None = None,
    description: str | None = None,
) -> ProductSubmission:
    actor.require(NegotiationPermission.SUPPLY)
    if uom.strip().upper() != "KG":
        raise ValidationFailed("Unit of measure must be KG", details={"uom": uom})
    if availability not in AVAILABILITY:
        raise ValidationFailed("Availability must be in_stock, limited or on_request", details={"availability": availability})
    money = currency.strip().upper()
    if money not in SUPPORTED_CURRENCIES:
        raise ValidationFailed("Currency must be INR or USD", details={"currency": currency})
    code = _code(proposed_code)
    pending = session.scalar(
        select(ProductSubmission.id).where(
            ProductSubmission.supplier_user_id == actor.user_id,
            ProductSubmission.proposed_code == code,
            ProductSubmission.status == "pending",
        )
    )
    if pending is not None:
        raise ValidationFailed(
            "You already have a pending submission for this product code",
            details={"productCode": code},
        )
    row = ProductSubmission(
        supplier_user_id=actor.user_id,
        proposed_code=code,
        name=_text(name, "name", 255),
        category=_text(category, "category", 64),
        subcategory=_optional(subcategory, 64),
        description=_optional(description, 4000),
        uom="KG",
        specifications=require_core_specifications(specifications),
        asking_price=asking_price,
        currency=money,
        minimum_quantity=minimum_quantity,
        maximum_quantity=catalogue_listings.resolve_maximum(availability, minimum_quantity, maximum_quantity),
        availability=availability,
    )
    session.add(row)
    session.flush()
    return row


def _load(session: Session, rows: list[ProductSubmission]) -> list[ProductSubmission]:
    if not rows:
        return []
    ids = [row.id for row in rows]
    return list(session.scalars(
        select(ProductSubmission)
        .where(ProductSubmission.id.in_(ids))
        .options(
            selectinload(ProductSubmission.supplier).selectinload(User.organisation),
            selectinload(ProductSubmission.product),
        )
        .order_by(ProductSubmission.created_at.desc())
    ))


def get(session: Session, submission_id: uuid.UUID) -> ProductSubmission:
    rows = list(session.scalars(select(ProductSubmission).where(ProductSubmission.id == submission_id)))
    loaded = _load(session, rows)
    if not loaded:
        raise NotFound("Submission not found", details={"submissionId": str(submission_id)})
    return loaded[0]


def own(session: Session, actor: Actor) -> list[ProductSubmission]:
    actor.require(NegotiationPermission.SUPPLY)
    rows = list(session.scalars(
        select(ProductSubmission).where(ProductSubmission.supplier_user_id == actor.user_id)
    ))
    return _load(session, rows)


def queue(session: Session, actor: Actor, *, status: str = "pending") -> list[ProductSubmission]:
    actor.require(PricingPermission.EDIT, PricingPermission.CONFIGURE)
    if status not in STATUSES:
        raise ValidationFailed("Status must be pending, accepted, or rejected", details={"status": status})
    rows = list(session.scalars(select(ProductSubmission).where(ProductSubmission.status == status)))
    return _load(session, rows)


def _pending(session: Session, submission_id: uuid.UUID) -> ProductSubmission:
    row = session.get(ProductSubmission, submission_id)
    if row is None:
        raise NotFound("Submission not found", details={"submissionId": str(submission_id)})
    if row.status != "pending":
        raise InvalidStateTransition("This submission has already been reviewed", details={"status": row.status})
    return row


def accept(
    session: Session, actor: Actor, submission_id: uuid.UUID, *, product_code: str | None = None
) -> ProductSubmission:
    actor.require(PricingPermission.EDIT, PricingPermission.CONFIGURE)
    row = _pending(session, submission_id)
    code = _code(product_code) if product_code else row.proposed_code
    product = catalogue.create_product(
        session, product_code=code, name=row.name, category=row.category, subcategory=row.subcategory,
        description=row.description, uom=row.uom, specifications=row.specifications,
    )
    catalogue_listings.insert_listing(
        session, supplier_user_id=row.supplier_user_id, product=product,
        minimum_quantity=row.minimum_quantity, asking_price=row.asking_price,
        currency=row.currency, availability=row.availability, maximum_quantity=row.maximum_quantity,
    )
    row.status = "accepted"
    row.product_id = product.id
    row.reviewed_by_user_id = actor.user_id
    row.reviewed_at = utcnow()
    session.flush()
    return row


def reject(session: Session, actor: Actor, submission_id: uuid.UUID, *, note: str) -> ProductSubmission:
    actor.require(PricingPermission.EDIT, PricingPermission.CONFIGURE)
    reason = note.strip()
    if not reason or len(reason) > 500:
        raise ValidationFailed("A review note is required", details={"field": "note"})
    row = _pending(session, submission_id)
    row.status = "rejected"
    row.review_note = reason
    row.reviewed_by_user_id = actor.user_id
    row.reviewed_at = utcnow()
    session.flush()
    return row
