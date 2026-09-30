"""Supplier profile read from Plenza organisations, listings, negotiations and orders.

Rates are calculated only where the underlying rows exist. On-time delivery stays
unavailable until an order stores a required date. Quality counts rejected fulfilment documents.
"""

import re
import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.catalogue.listings import can_supply
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.identity.constants import IdentityPermission
from app.identity.service import Actor
from app.models.identity import Organisation, User
from app.models.listing import SupplierListing
from app.models.negotiation import Negotiation, NegotiationVersion
from app.models.order import Order
from app.negotiation.constants import NegotiationPermission, NegotiationStatus

PIN_PREFIX = re.compile(r"^[1-9][0-9]{2}$")
VERIFICATION = ("unverified", "pending", "verified")
HISTORY_LIMIT = 8

ON_TIME_NOTE = "Orders do not store a required delivery date yet, so on-time delivery is not calculated."
QUALITY_EMPTY = "No fulfilment documents are stored for this supplier yet."
QUALITY_NOTE = "Rejected fulfilment documents divided by the documents stored on this supplier's orders."
ACCEPTANCE_EMPTY = "No negotiation has been accepted, rejected, or cancelled yet."
ACCEPTANCE_NOTE = "Accepted negotiations divided by negotiations that were accepted, rejected, or cancelled."
CANCELLATION_EMPTY = "No orders yet, so a cancellation rate is not calculated."
CANCELLATION_NOTE = "Cancelled orders divided by all orders for this supplier."
RESPONSE_EMPTY = "No supplier reply has followed a buyer offer yet."
RESPONSE_NOTE = "Average hours from a buyer offer to the next supplier offer."


def _percent(count: int, total: int) -> str | None:
    if total <= 0:
        return None
    value = (Decimal(count) * Decimal(100) / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:.2f}"


def _rate(count: int, total: int, *, empty: str, note: str) -> dict:
    if total <= 0:
        return {"available": False, "note": empty, "count": 0, "total": 0, "percent": None}
    return {"available": True, "note": note, "count": count, "total": total, "percent": _percent(count, total)}


def _unavailable(note: str) -> dict:
    return {"available": False, "note": note, "count": 0, "total": 0, "percent": None}


def _viewer(session: Session, actor: Actor) -> User:
    user = session.get(User, actor.user_id)
    if user is None:
        raise PermissionDenied("Sign in to continue.")
    return user


def _organisation(session: Session, organisation_id: uuid.UUID) -> Organisation:
    org = session.get(Organisation, organisation_id)
    if org is None or org.org_type != "supplier":
        raise NotFound("Supplier not found", details={"organisationId": str(organisation_id)})
    return org


def _require_view(session: Session, actor: Actor, org: Organisation) -> User:
    user = _viewer(session, actor)
    if user.organisation_id == org.id:
        return user
    if actor.has(NegotiationPermission.BUY) or actor.has(IdentityPermission.MANAGE):
        return user
    raise PermissionDenied("You cannot view this supplier.")


def _members(session: Session, org: Organisation) -> list[User]:
    return list(session.scalars(select(User).where(User.organisation_id == org.id, User.is_system.is_(False))))


def _regions(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    regions = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        prefix = item.get("pinPrefix") or item.get("pin_prefix")
        if label:
            regions.append({"label": label, "pin_prefix": str(prefix) if prefix else None})
    return regions


def _clean_regions(regions: list[dict]) -> list[dict]:
    cleaned = []
    seen: set[str] = set()
    for item in regions:
        label = item["label"].strip()
        key = label.casefold()
        if key in seen:
            raise ValidationFailed("Each service region needs its own name", details={"label": label})
        seen.add(key)
        prefix = (item.get("pin_prefix") or "").strip() or None
        if prefix is not None and PIN_PREFIX.fullmatch(prefix) is None:
            raise ValidationFailed(
                "A service region PIN prefix must be the first three digits of a PIN",
                details={"pinPrefix": prefix},
            )
        cleaned.append({"label": label, "pin_prefix": prefix})
    return cleaned


def _rates(negotiations: list[Negotiation], orders: list[Order], documents: list | None = None) -> dict:
    decided = [item for item in negotiations if item.status in (
        NegotiationStatus.ACCEPTED, NegotiationStatus.REJECTED, NegotiationStatus.CANCELLED,
    )]
    accepted = sum(1 for item in decided if item.status == NegotiationStatus.ACCEPTED)
    cancelled_orders = sum(1 for item in orders if item.status == "cancelled")
    samples = _response_samples(negotiations)
    files = documents or []
    rejected = sum(1 for item in files if item.status == "rejected")
    return {
        "response_time": {
            "available": bool(samples),
            "note": RESPONSE_NOTE if samples else RESPONSE_EMPTY,
            "sample_count": len(samples),
            "average_hours": _hours(samples),
        },
        "acceptance": _rate(accepted, len(decided), empty=ACCEPTANCE_EMPTY, note=ACCEPTANCE_NOTE),
        "order_cancellation": _rate(
            cancelled_orders, len(orders), empty=CANCELLATION_EMPTY, note=CANCELLATION_NOTE,
        ),
        "on_time_delivery": _unavailable(ON_TIME_NOTE),
        "quality": _rate(rejected, len(files), empty=QUALITY_EMPTY, note=QUALITY_NOTE),
    }


def performance(session: Session, organisation_id: uuid.UUID) -> dict:
    """Phase 1 rates for one organisation. Unavailable metrics stay unavailable."""
    member_ids = list(session.scalars(
        select(User.id).where(User.organisation_id == organisation_id, User.is_system.is_(False))
    ))
    if not member_ids:
        return _rates([], [])
    negotiations = list(session.scalars(
        select(Negotiation)
        .where(Negotiation.supplier_user_id.in_(member_ids))
        .options(selectinload(Negotiation.versions))
    ))
    orders = list(session.scalars(select(Order).where(Order.supplier_user_id.in_(member_ids))))
    from app.models.fulfilment import OrderDocument
    files = []
    if orders:
        files = list(session.scalars(select(OrderDocument).where(OrderDocument.order_id.in_([item.id for item in orders]))))
    return _rates(negotiations, orders, files)


def _response_samples(negotiations: list[Negotiation]) -> list[float]:
    samples: list[float] = []
    for negotiation in negotiations:
        waiting_since = None
        for version in negotiation.versions:
            if version.created_by_user_id == negotiation.supplier_user_id:
                if waiting_since is not None:
                    samples.append((version.created_at - waiting_since).total_seconds())
                    waiting_since = None
            else:
                waiting_since = version.created_at
    return samples


def _hours(samples: list[float]) -> str | None:
    if not samples:
        return None
    average = (Decimal(str(sum(samples))) / Decimal(len(samples)) / Decimal(3600)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"{average:.2f}"


def _history_for_viewer(actor: Actor, viewer: User, org: Organisation, negotiations, orders):
    """Company members see their book. A buyer sees only deals where they are the buyer."""
    if viewer.organisation_id == org.id:
        return negotiations, orders
    return (
        [item for item in negotiations if item.buyer_user_id == actor.user_id],
        [item for item in orders if item.buyer_user_id == actor.user_id],
    )


def profile(session: Session, actor: Actor, organisation_id: uuid.UUID) -> dict:
    org = _organisation(session, organisation_id)
    viewer = _require_view(session, actor, org)
    member_ids = [user.id for user in _members(session, org)]
    show_email = viewer.organisation_id == org.id or actor.has(IdentityPermission.MANAGE)

    listings = []
    if member_ids:
        rows = session.scalars(
            select(SupplierListing)
            .join(User, User.id == SupplierListing.supplier_user_id)
            .where(
                User.organisation_id == org.id,
                SupplierListing.is_active.is_(True),
                User.is_active.is_(True),
            )
            .options(selectinload(SupplierListing.product), selectinload(SupplierListing.supplier))
        )
        listings = [row for row in rows if can_supply(session, row.supplier)]

    negotiations: list[Negotiation] = []
    orders: list[Order] = []
    if member_ids:
        negotiations = list(
            session.scalars(
                select(Negotiation)
                .where(Negotiation.supplier_user_id.in_(member_ids))
                .options(
                    selectinload(Negotiation.versions).selectinload(NegotiationVersion.created_by),
                    selectinload(Negotiation.product),
                )
                .order_by(Negotiation.updated_at.desc())
            )
        )
        orders = list(
            session.scalars(
                select(Order)
                .where(Order.supplier_user_id.in_(member_ids))
                .options(selectinload(Order.product))
                .order_by(Order.updated_at.desc())
            )
        )

    rates = _rates(negotiations, orders)
    visible_quotes, visible_orders = _history_for_viewer(actor, viewer, org, negotiations, orders)
    people = [user for user in _members(session, org) if user.is_active]

    return {
        "organisation_id": org.id,
        "name": org.name,
        "verification_status": org.verification_status,
        "dispatch_pin": org.dispatch_pin,
        "dispatch_label": org.dispatch_label,
        "service_regions": _regions(org.service_regions),
        "people": [{"name": user.full_name, "email": user.email if show_email else None} for user in people],
        "products": [
            {
                "product_code": row.product.product_code,
                "name": row.product.name,
                "uom": row.uom,
                "minimum_quantity": f"{row.minimum_quantity.normalize():f}",
                "asking_price": {"amount": f"{row.asking_price:.4f}", "currency": row.currency},
                "availability": row.availability,
            }
            for row in listings
        ],
        **rates,
        "quote_count": len(negotiations),
        "order_count": len(orders),
        "quotes": [
            {
                "id": item.id,
                "reference": item.negotiation_number,
                "product_name": item.product.name,
                "status": item.status,
                "latest_offer": (
                    {"amount": f"{item.versions[-1].offered_price:.4f}", "currency": item.currency}
                    if item.versions else None
                ),
                "updated_at": item.updated_at,
            }
            for item in visible_quotes[:HISTORY_LIMIT]
        ],
        "orders": [
            {
                "id": item.id,
                "reference": item.order_number,
                "product_name": item.product.name,
                "status": item.status,
                "total_value": {"amount": f"{item.total_value:.2f}", "currency": item.currency},
                "updated_at": item.updated_at,
            }
            for item in visible_orders[:HISTORY_LIMIT]
        ],
        "can_edit_regions": viewer.organisation_id == org.id and actor.has(NegotiationPermission.SUPPLY),
        "can_set_verification": actor.has(IdentityPermission.MANAGE),
    }


def set_regions(session: Session, actor: Actor, organisation_id: uuid.UUID, regions: list[dict]) -> dict:
    org = _organisation(session, organisation_id)
    viewer = _viewer(session, actor)
    if viewer.organisation_id != org.id or not actor.has(NegotiationPermission.SUPPLY):
        raise PermissionDenied("Only this supplier can declare service regions.")
    org.service_regions = _clean_regions(regions)
    session.flush()
    return profile(session, actor, organisation_id)


def set_verification(session: Session, actor: Actor, organisation_id: uuid.UUID, status: str) -> dict:
    actor.require(IdentityPermission.MANAGE)
    if status not in VERIFICATION:
        raise ValidationFailed("Verification status is not recognised", details={"status": status})
    org = _organisation(session, organisation_id)
    org.verification_status = status
    session.flush()
    return profile(session, actor, organisation_id)
