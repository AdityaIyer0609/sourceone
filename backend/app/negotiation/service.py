"""Negotiation V1 lifecycle.

The reference value snapshotted at creation is the average of supplier asking prices when suppliers
are listing the material, otherwise the published benchmark. Offer = proposed price (an immutable
version). Negotiated price = the accepted version's offered price. Freight is an estimate for this
order and is not part of the offered price.
"""

import re
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.catalogue.specifications import requirement_snapshot
from app.catalogue import market_average
from app.catalogue import products as catalogue
from app.core.clock import business_today, utcnow
from app.freight import service as freight
from app.core.errors import (
    AwaitingCounterparty,
    CurrencyUnitMismatch,
    InvalidStateTransition,
    NegotiationClosed,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from app.identity.service import Actor, get_user_permissions
from app.models.identity import User
from app.models.negotiation import Negotiation, NegotiationVersion
from app.negotiation.constants import (
    ACTIVE_STATUSES,
    NUMBER_SEQUENCE,
    TERMINAL_STATUSES,
    BenchmarkSnapshotState,
    NegotiationPermission,
    NegotiationStatus,
)
from app.pricing import read_model, repository
from app.pricing.constants import SUPPORTED_CURRENCIES

Role = Literal["buyer", "supplier"]


def role_of(actor: Actor, negotiation: Negotiation) -> Role | None:
    if actor.user_id == negotiation.buyer_user_id and actor.has(NegotiationPermission.BUY):
        return "buyer"
    if actor.user_id == negotiation.supplier_user_id and actor.has(NegotiationPermission.SUPPLY):
        return "supplier"
    return None


def _latest(negotiation: Negotiation) -> NegotiationVersion | None:
    return negotiation.versions[-1] if negotiation.versions else None


def awaiting_party(negotiation: Negotiation) -> Role | None:
    """The party whose move it is on an active negotiation."""
    if negotiation.status == NegotiationStatus.DRAFT:
        return "buyer"
    latest = _latest(negotiation)
    if negotiation.status not in ACTIVE_STATUSES or latest is None:
        return None
    return "supplier" if latest.created_by_user_id == negotiation.buyer_user_id else "buyer"


def allowed_actions(actor: Actor, negotiation: Negotiation) -> dict[str, bool]:
    role = role_of(actor, negotiation)
    my_turn = role is not None and awaiting_party(negotiation) == role
    active = negotiation.status in ACTIVE_STATUSES
    return {
        "offer": my_turn,
        "accept": my_turn and active,
        "reject": my_turn and active,
        "cancel": role == "buyer" and negotiation.status not in TERMINAL_STATUSES,
    }


def _next_number(session: Session, now: datetime) -> str:
    sequence = session.scalar(text(f"SELECT nextval('{NUMBER_SEQUENCE}')"))
    return f"NEG-{business_today(now).year}-{sequence:04d}"


def list_suppliers(session: Session, actor: Actor) -> list[User]:
    """Active users who can supply. Buyers pick one when starting a negotiation."""
    actor.require(NegotiationPermission.BUY)
    users = session.scalars(
        select(User).where(User.is_active.is_(True), User.is_system.is_(False)).options(selectinload(User.organisation))
    ).all()
    return [
        user for user in users
        if user.id != actor.user_id and NegotiationPermission.SUPPLY in get_user_permissions(session, user.id)
    ]


def _resolve_supplier(session: Session, supplier_user_id: uuid.UUID | None) -> User:
    if supplier_user_id is not None:
        supplier = session.get(User, supplier_user_id)
        if (
            supplier is None or not supplier.is_active or supplier.is_system
            or NegotiationPermission.SUPPLY not in get_user_permissions(session, supplier.id)
        ):
            raise ValidationFailed("Supplier not found or not allowed to negotiate",
                                   details={"supplierUserId": str(supplier_user_id)})
        return supplier
    # V1 demo convenience: with a single eligible supplier the buyer need not choose one.
    candidates = [
        user for user in session.scalars(
            select(User).where(User.is_active.is_(True), User.is_system.is_(False))
        )
        if NegotiationPermission.SUPPLY in get_user_permissions(session, user.id)
    ]
    if len(candidates) != 1:
        raise ValidationFailed("Choose a supplier for this negotiation", details={"field": "supplierUserId"})
    return candidates[0]


def _check_offer_terms(negotiation: Negotiation, currency: str | None, uom: str | None) -> None:
    if (currency and currency.upper() != negotiation.currency) or (uom and uom.upper() != negotiation.uom):
        raise CurrencyUnitMismatch(
            f"Offers on this negotiation must be in {negotiation.currency} per {negotiation.uom}",
            details={"currency": negotiation.currency, "uom": negotiation.uom},
        )


def _latest_supplier_date(negotiation: Negotiation) -> date | None:
    for version in reversed(negotiation.versions):
        if version.delivery_date is not None:
            return version.delivery_date
    return None


def delivery_note(negotiation: Negotiation) -> str | None:
    """How the supplier's latest stated date sits against the buyer's fixed request."""
    if negotiation.required_by is None:
        return None
    stated = _latest_supplier_date(negotiation)
    if stated is None:
        return "Delivery date has not been offered"
    delta = (stated - negotiation.required_by).days
    if delta == 0:
        return "On the requested date"
    days = abs(delta)
    unit = "day" if days == 1 else "days"
    if delta < 0:
        return f"{days} {unit} before the requested date"
    return f"{days} {unit} after the requested date"


def _supplier_delivery_date(negotiation: Negotiation, actor: Actor, supplied: date | None) -> date | None:
    """Only a supplier states a date. A later offer keeps the previous date when they leave it unchanged."""
    if role_of(actor, negotiation) != "supplier":
        if supplied is not None:
            raise ValidationFailed(
                "The requested delivery date is fixed. Only the supplier states a delivery date.",
                details={"field": "deliveryDate"},
            )
        return None
    if supplied is not None:
        return supplied
    previous = _latest_supplier_date(negotiation)
    if negotiation.required_by is not None and previous is None:
        raise ValidationFailed("State the date you can deliver", details={"field": "deliveryDate"})
    return previous


def _add_version(
    session: Session, negotiation: Negotiation, actor: Actor, *, price: Decimal, quantity: Decimal,
    message: str | None, now: datetime, delivery_date: date | None = None,
) -> NegotiationVersion:
    version = NegotiationVersion(
        negotiation_id=negotiation.id,
        version_number=len(negotiation.versions) + 1,
        created_by_user_id=actor.user_id,
        offered_price=price,
        currency=negotiation.currency,
        quantity=quantity,
        uom=negotiation.uom,
        message=(message or "").strip() or None,
        delivery_date=delivery_date,
        created_at=now,
    )
    session.add(version)
    negotiation.versions.append(version)
    return version


def _freight_fields(
    session: Session,
    supplier_user_id: uuid.UUID,
    product_code: str,
    quantity: Decimal,
    destination_pin: str | None,
    freight_basis: str,
) -> dict:
    """Estimate only. The amount is never written into the offered price."""
    if not destination_pin:
        return {}
    pin = destination_pin.strip()
    if not re.fullmatch(r"[1-9][0-9]{5}", pin):
        raise ValidationFailed("Delivery PIN must be 6 digits", details={"destinationPin": pin})
    if freight_basis not in ("standard", "distance"):
        raise ValidationFailed("Choose normal freight or road distance", details={"freightBasis": freight_basis})
    try:
        result = freight.estimate(
            session,
            supplier_user_id=supplier_user_id,
            product_code=product_code,
            quantity=quantity,
            destination_pin=pin,
            include_distance=freight_basis == "distance",
        )
    except NotFound:
        return {"destination_pin": pin, "freight_status": "on_request", "freight_basis": freight_basis}
    if freight_basis == "distance":
        estimated = result["distance_status"] == "estimated" and result["distance_freight"] is not None
        return {
            "destination_pin": pin,
            "freight_status": "estimated" if estimated else "on_request",
            "freight_amount": result["distance_freight"] if estimated else None,
            "freight_match": "distance" if estimated else None,
            "freight_basis": freight_basis,
        }
    estimated = result["freight"] is not None
    return {
        "destination_pin": pin,
        "freight_status": "estimated" if estimated else "on_request",
        "freight_amount": result["freight"] if estimated else None,
        "freight_match": result["match"] if estimated else None,
        "freight_basis": freight_basis,
    }


def create_negotiation(
    session: Session,
    actor: Actor,
    *,
    product_code: str,
    quantity: Decimal,
    series_code: str | None = None,
    offered_price: Decimal | None = None,
    message: str | None = None,
    currency: str | None = None,
    supplier_user_id: uuid.UUID | None = None,
    destination_pin: str | None = None,
    freight_basis: str = "standard",
    required_by: date | None = None,
    payment_terms: str | None = None,
    requirements: list | None = None,
    now: datetime | None = None,
) -> Negotiation:
    actor.require(NegotiationPermission.BUY)
    now = now or utcnow()
    product = catalogue.get_active_product(session, product_code)
    options = catalogue.buyer_series(product)
    if series_code:
        series = next((s for s in options if s.code == series_code), None)
        if series is None:
            raise ValidationFailed(f"Rate series {series_code!r} is not available for this product",
                                   details={"seriesCode": series_code})
    else:
        series = options[0] if options else None

    negotiation_currency = series.currency if series else (currency or "").upper()
    if currency and currency.upper() != negotiation_currency:
        raise CurrencyUnitMismatch(f"This product's benchmark is in {negotiation_currency}")
    if negotiation_currency not in SUPPORTED_CURRENCIES:
        raise ValidationFailed("A supported currency is required", details={"field": "currency"})

    snapshot = dict(benchmark_state=BenchmarkSnapshotState.RATE_ON_REQUEST)
    if series is not None:
        snapshot["benchmark_series_code"] = series.code
        snapshot["benchmark_basis"] = f"{series.price_basis}/{series.tax_basis}"
        current = read_model.resolve_current(repository.timelines(session, [series.id]).get(series.id, []), now)
        if current.benchmark is not None and current.freshness is not None:
            snapshot.update(
                benchmark_state=current.freshness.state,
                benchmark_rate_id=current.benchmark.id,
                benchmark_rate_snapshot=current.benchmark.value,
                benchmark_as_of=current.freshness.as_of_date,
            )

    average = market_average.current_average(session, product.id, negotiation_currency)
    if average is not None:
        snapshot.update(
            benchmark_state=BenchmarkSnapshotState.FRESH,
            benchmark_rate_id=None,
            benchmark_rate_snapshot=average,
            benchmark_as_of=business_today(now),
            benchmark_basis="ASKING_AVERAGE/GST_EXCLUDED",
        )

    supplier = _resolve_supplier(session, supplier_user_id)
    if supplier.id == actor.user_id:
        raise ValidationFailed("Buyer and supplier must be different users")
    negotiation = Negotiation(
        negotiation_number=_next_number(session, now),
        buyer_user_id=actor.user_id,
        supplier_user_id=supplier.id,
        product_id=product.id,
        rate_series_id=series.id if series else None,
        quantity=quantity,
        uom=product.uom,
        currency=negotiation_currency,
        status=NegotiationStatus.DRAFT,
        required_by=required_by,
        payment_terms=(payment_terms or "").strip() or None,
        requirements=requirements if requirements is not None else requirement_snapshot(product),
        created_at=now,
        updated_at=now,
        **snapshot,
        **_freight_fields(session, supplier.id, product_code, quantity, destination_pin, freight_basis),
    )
    session.add(negotiation)
    session.flush()
    if offered_price is not None:
        _add_version(session, negotiation, actor, price=offered_price, quantity=quantity, message=message, now=now)
        negotiation.status = NegotiationStatus.OPEN
    session.flush()
    return negotiation


def _query():
    return select(Negotiation).options(
        selectinload(Negotiation.versions).selectinload(NegotiationVersion.created_by),
        selectinload(Negotiation.buyer).selectinload(User.organisation),
        selectinload(Negotiation.supplier).selectinload(User.organisation),
        selectinload(Negotiation.product),
    )


def _visibility(actor: Actor):
    clauses = []
    if actor.has(NegotiationPermission.BUY):
        clauses.append(Negotiation.buyer_user_id == actor.user_id)
    if actor.has(NegotiationPermission.SUPPLY):
        # Drafts have not been sent yet, so the supplier cannot see them.
        clauses.append((Negotiation.supplier_user_id == actor.user_id) & (Negotiation.status != NegotiationStatus.DRAFT))
    return or_(*clauses)


def list_negotiations(session: Session, actor: Actor, *, status: str | None = None) -> Sequence[Negotiation]:
    actor.require(NegotiationPermission.BUY, NegotiationPermission.SUPPLY)
    stmt = _query().where(_visibility(actor)).order_by(Negotiation.updated_at.desc(), Negotiation.negotiation_number)
    if status:
        stmt = stmt.where(Negotiation.status == status)
    return session.scalars(stmt).all()


def get_negotiation(session: Session, actor: Actor, negotiation_id: uuid.UUID, *, for_update: bool = False) -> Negotiation:
    actor.require(NegotiationPermission.BUY, NegotiationPermission.SUPPLY)
    stmt = _query().where(Negotiation.id == negotiation_id, _visibility(actor))
    if for_update:
        stmt = stmt.with_for_update(of=Negotiation)
    negotiation = session.scalar(stmt)
    if negotiation is None:
        raise NotFound("Negotiation not found", details={"negotiationId": str(negotiation_id)})
    return negotiation


def _participant_move(actor: Actor, negotiation: Negotiation, action: str) -> Role:
    if negotiation.status in TERMINAL_STATUSES:
        raise NegotiationClosed(f"Negotiation is {negotiation.status}; no further {action} is possible",
                                details={"status": negotiation.status})
    role = role_of(actor, negotiation)
    if role is None:
        raise PermissionDenied("Only the buyer or assigned supplier can act on this negotiation")
    if awaiting_party(negotiation) != role:
        raise AwaitingCounterparty("Waiting for the other party to respond to the latest offer",
                                   details={"awaiting": awaiting_party(negotiation)})
    return role


def make_offer(
    session: Session, actor: Actor, negotiation_id: uuid.UUID, *, price: Decimal, quantity: Decimal | None = None,
    message: str | None = None, currency: str | None = None, uom: str | None = None,
    delivery_date: date | None = None, now: datetime | None = None,
) -> Negotiation:
    now = now or utcnow()
    negotiation = get_negotiation(session, actor, negotiation_id, for_update=True)
    _participant_move(actor, negotiation, "offer")
    _check_offer_terms(negotiation, currency, uom)
    latest = _latest(negotiation)
    _add_version(
        session, negotiation, actor, price=price,
        quantity=quantity or (latest.quantity if latest else negotiation.quantity), message=message, now=now,
        delivery_date=_supplier_delivery_date(negotiation, actor, delivery_date),
    )
    negotiation.status = NegotiationStatus.OPEN if negotiation.status == NegotiationStatus.DRAFT else NegotiationStatus.COUNTERED
    negotiation.updated_at = now
    session.flush()
    return negotiation


def _close(negotiation: Negotiation, actor: Actor, status: NegotiationStatus, now: datetime, reason: str | None):
    negotiation.status = status
    negotiation.closed_at = now
    negotiation.closed_by_user_id = actor.user_id
    negotiation.closed_reason = (reason or "").strip() or None
    negotiation.updated_at = now


def accept_offer(session: Session, actor: Actor, negotiation_id: uuid.UUID, *, now: datetime | None = None) -> Negotiation:
    now = now or utcnow()
    negotiation = get_negotiation(session, actor, negotiation_id, for_update=True)
    if negotiation.status == NegotiationStatus.DRAFT:
        raise InvalidStateTransition("A draft has no offer to accept", details={"from": "draft", "to": "accepted"})
    _participant_move(actor, negotiation, "acceptance")
    negotiation.accepted_version_id = _latest(negotiation).id
    _close(negotiation, actor, NegotiationStatus.ACCEPTED, now, None)
    session.flush()
    return negotiation


def reject_offer(
    session: Session, actor: Actor, negotiation_id: uuid.UUID, *, reason: str | None = None, now: datetime | None = None
) -> Negotiation:
    now = now or utcnow()
    negotiation = get_negotiation(session, actor, negotiation_id, for_update=True)
    if negotiation.status == NegotiationStatus.DRAFT:
        raise InvalidStateTransition("A draft has no offer to reject; cancel it instead",
                                     details={"from": "draft", "to": "rejected"})
    _participant_move(actor, negotiation, "rejection")
    _close(negotiation, actor, NegotiationStatus.REJECTED, now, reason)
    session.flush()
    return negotiation


def cancel_negotiation(
    session: Session, actor: Actor, negotiation_id: uuid.UUID, *, reason: str | None = None, now: datetime | None = None
) -> Negotiation:
    now = now or utcnow()
    negotiation = get_negotiation(session, actor, negotiation_id, for_update=True)
    if negotiation.status in TERMINAL_STATUSES:
        raise NegotiationClosed(f"Negotiation is already {negotiation.status}", details={"status": negotiation.status})
    if role_of(actor, negotiation) != "buyer":
        raise PermissionDenied("Only the buyer can cancel a negotiation")
    _close(negotiation, actor, NegotiationStatus.CANCELLED, now, reason)
    session.flush()
    return negotiation


def negotiated_version(negotiation: Negotiation) -> NegotiationVersion | None:
    if negotiation.accepted_version_id is None:
        return None
    return next(v for v in negotiation.versions if v.id == negotiation.accepted_version_id)


def answer_requirement(
    session: Session, actor: Actor, negotiation_id: uuid.UUID, key: str, *,
    status: str, comment: str | None = None, now: datetime | None = None,
) -> Negotiation:
    """The supplier answers one frozen requirement. This does not change the product."""
    from app.models.fulfilment import RequirementResponse

    now = now or utcnow()
    negotiation = get_negotiation(session, actor, negotiation_id, for_update=True)
    if role_of(actor, negotiation) != "supplier":
        raise PermissionDenied("Only the supplier on this negotiation can answer a requirement")
    if negotiation.status in (NegotiationStatus.REJECTED, NegotiationStatus.CANCELLED):
        raise NegotiationClosed("This negotiation is closed", details={"status": negotiation.status})
    rows = negotiation.requirements or []
    if key not in {row["key"] for row in rows}:
        raise ValidationFailed("That requirement is not on this negotiation", details={"key": key})
    if status not in ("met", "not_met"):
        raise ValidationFailed("Say whether the requirement is met", details={"status": status})
    note = (comment or "").strip() or None
    if note is not None and len(note) > 500:
        raise ValidationFailed("The comment is too long", details={"field": "comment"})
    existing = session.scalar(
        select(RequirementResponse).where(
            RequirementResponse.negotiation_id == negotiation.id, RequirementResponse.requirement_key == key,
        )
    )
    if existing is None:
        session.add(RequirementResponse(
            negotiation_id=negotiation.id, requirement_key=key, status=status, comment=note,
            updated_by_user_id=actor.user_id, updated_at=now,
        ))
    else:
        existing.status = status
        existing.comment = note
        existing.updated_by_user_id = actor.user_id
        existing.updated_at = now
    session.flush()
    return negotiation


def requirement_answers(session: Session, negotiation_id: uuid.UUID) -> list:
    from app.models.fulfilment import RequirementResponse

    return list(session.scalars(
        select(RequirementResponse).where(RequirementResponse.negotiation_id == negotiation_id).order_by(RequirementResponse.requirement_key)
    ).all())
