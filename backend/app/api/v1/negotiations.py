"""Buyer/supplier negotiations. Each party only ever sees negotiations it is part of."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require_any
from app.api.v1.pricing_presenters import money, quote_position
from app.catalogue import market_average
from app.catalogue.listings import supply_note
from app.identity.service import Actor
from app.models.listing import SupplierListing
from app.models.negotiation import Negotiation, NegotiationVersion
from app.negotiation import service
from app.negotiation.constants import NegotiationPermission, NegotiationStatus
from app.schemas import negotiation as schemas

router = APIRouter(prefix="/negotiations", tags=["negotiations"])

Participant = Annotated[Actor, Depends(require_any(NegotiationPermission.BUY, NegotiationPermission.SUPPLY))]


def quantity_text(value: Decimal) -> str:
    return f"{value.normalize():f}"


def party_out(user) -> schemas.PartyOut:
    return schemas.PartyOut(
        name=user.full_name, organisation=user.organisation.name, organisation_id=user.organisation_id,
    )


def _version(negotiation: Negotiation, version: NegotiationVersion) -> schemas.VersionOut:
    return schemas.VersionOut(
        version_number=version.version_number,
        offered_by="buyer" if version.created_by_user_id == negotiation.buyer_user_id else "supplier",
        author=version.created_by.full_name,
        offered_price=money(version.offered_price, version.currency),
        quantity=quantity_text(version.quantity),
        uom=version.uom,
        message=version.message,
        delivery_date=version.delivery_date,
        created_at=version.created_at,
    )


def _listing(db: Session, negotiation: Negotiation) -> SupplierListing | None:
    return db.scalar(select(SupplierListing).where(
        SupplierListing.supplier_user_id == negotiation.supplier_user_id,
        SupplierListing.product_id == negotiation.product_id,
    ))


def _supply_note(db: Session, negotiation: Negotiation) -> str | None:
    listing = _listing(db, negotiation)
    if listing is None:
        return None
    if listing.sold_out:
        return "Sold out."
    latest = negotiation.versions[-1] if negotiation.versions else None
    if latest is not None and latest.quantity > negotiation.quantity and listing.maximum_quantity is not None:
        left = f"{negotiation.quantity.normalize():f}"
        return f"Only {left} {negotiation.uom.lower()} is still available, so this negotiation is now for {left} {negotiation.uom.lower()}."
    return supply_note(listing, negotiation.quantity)


def _present(actor: Actor, db: Session, negotiation: Negotiation) -> schemas.NegotiationOut:
    accepted = service.negotiated_version(negotiation)
    latest = negotiation.versions[-1] if negotiation.versions else None
    average = market_average.current_average(db, negotiation.product_id, negotiation.currency)
    return schemas.NegotiationOut(
        id=negotiation.id,
        negotiation_number=negotiation.negotiation_number,
        status=negotiation.status,
        product=schemas.NegotiationProductOut(
            product_code=negotiation.product.product_code, name=negotiation.product.name,
            category=negotiation.product.category,
        ),
        quantity=quantity_text(negotiation.quantity),
        uom=negotiation.uom,
        currency=negotiation.currency,
        buyer=party_out(negotiation.buyer),
        supplier=party_out(negotiation.supplier),
        supplier_user_id=negotiation.supplier_user_id,
        benchmark=schemas.BenchmarkSnapshotOut(
            state=negotiation.benchmark_state,
            value=money(negotiation.benchmark_rate_snapshot, negotiation.currency),
            as_of_date=negotiation.benchmark_as_of,
            series_code=negotiation.benchmark_series_code,
            basis=negotiation.benchmark_basis,
        ),
        quote=quote_position(
            latest.offered_price if latest is not None else None,
            negotiation.benchmark_rate_snapshot,
            average,
            negotiation.currency,
        ),
        versions=[_version(negotiation, v) for v in negotiation.versions],
        negotiated=schemas.NegotiatedPriceOut(
            version_number=accepted.version_number,
            price=money(accepted.offered_price, accepted.currency),
            quantity=quantity_text(accepted.quantity),
            uom=accepted.uom,
        ) if accepted else None,
        awaiting=service.awaiting_party(negotiation),
        viewer_role=service.role_of(actor, negotiation),
        allowed_actions=schemas.AllowedActionsOut(**service.allowed_actions(actor, negotiation)),
        created_at=negotiation.created_at,
        updated_at=negotiation.updated_at,
        closed_at=negotiation.closed_at,
        closed_reason=negotiation.closed_reason,
        destination_pin=negotiation.destination_pin,
        freight_status=negotiation.freight_status,
        freight=money(negotiation.freight_amount, negotiation.currency) if negotiation.freight_amount is not None else None,
        freight_match=negotiation.freight_match,
        freight_basis=negotiation.freight_basis,
        required_by=negotiation.required_by,
        payment_terms=negotiation.payment_terms,
        requirements=[schemas.RequirementOut(**row) for row in (negotiation.requirements or [])],
        requirement_responses=[
            schemas.RequirementResponseOut(key=row.requirement_key, status=row.status, comment=row.comment)
            for row in service.requirement_answers(db, negotiation.id)
        ],
        supply_note=_supply_note(db, negotiation),
        delivery_note=service.delivery_note(negotiation),
        available_quantity=(
            quantity_text(stock.maximum_quantity)
            if (stock := _listing(db, negotiation)) is not None and not stock.sold_out and stock.maximum_quantity is not None
            else None
        ),
        sold_out=bool(stock and stock.sold_out),
    )


@router.post("", response_model=schemas.NegotiationOut, status_code=201)
def create_negotiation(body: schemas.CreateNegotiationIn, db: DbSession, actor: Participant):
    negotiation = service.create_negotiation(
        db, actor, product_code=body.product_code, series_code=body.series_code, quantity=body.quantity,
        offered_price=body.offered_price, message=body.message, currency=body.currency,
        supplier_user_id=body.supplier_user_id, destination_pin=body.destination_pin,
        freight_basis=body.freight_basis,
    )
    db.commit()
    return _present(actor, db, service.get_negotiation(db, actor, negotiation.id))


@router.get("/suppliers", response_model=list[schemas.SupplierOptionOut])
def list_suppliers(db: DbSession, actor: Participant):
    return [
        schemas.SupplierOptionOut(id=user.id, name=user.full_name, organisation=user.organisation.name)
        for user in service.list_suppliers(db, actor)
    ]


@router.get("", response_model=list[schemas.NegotiationOut])
def list_negotiations(db: DbSession, actor: Participant, status: NegotiationStatus | None = None):
    return [_present(actor, db, n) for n in service.list_negotiations(db, actor, status=status)]


@router.get("/{negotiation_id}", response_model=schemas.NegotiationOut)
def get_negotiation(negotiation_id: uuid.UUID, db: DbSession, actor: Participant):
    return _present(actor, db, service.get_negotiation(db, actor, negotiation_id))


@router.post("/{negotiation_id}/offers", response_model=schemas.NegotiationOut, status_code=201)
def make_offer(negotiation_id: uuid.UUID, body: schemas.OfferIn, db: DbSession, actor: Participant):
    negotiation = service.make_offer(
        db, actor, negotiation_id, price=body.offered_price, quantity=body.quantity, message=body.message,
        currency=body.currency, uom=body.uom, delivery_date=body.delivery_date,
    )
    db.commit()
    return _present(actor, db, negotiation)


@router.post("/{negotiation_id}/requirements/{key}", response_model=schemas.NegotiationOut)
def answer_requirement(
    negotiation_id: uuid.UUID, key: str, body: schemas.RequirementAnswerIn, db: DbSession, actor: Participant,
):
    negotiation = service.answer_requirement(
        db, actor, negotiation_id, key, status=body.status, comment=body.comment,
    )
    db.commit()
    return _present(actor, db, negotiation)


@router.post("/{negotiation_id}/accept", response_model=schemas.NegotiationOut)
def accept(negotiation_id: uuid.UUID, db: DbSession, actor: Participant):
    negotiation = service.accept_offer(db, actor, negotiation_id)
    db.commit()
    return _present(actor, db, negotiation)


@router.post("/{negotiation_id}/reject", response_model=schemas.NegotiationOut)
def reject(negotiation_id: uuid.UUID, db: DbSession, actor: Participant, body: schemas.CloseIn | None = None):
    negotiation = service.reject_offer(db, actor, negotiation_id, reason=body.reason if body else None)
    db.commit()
    return _present(actor, db, negotiation)


@router.post("/{negotiation_id}/cancel", response_model=schemas.NegotiationOut)
def cancel(negotiation_id: uuid.UUID, db: DbSession, actor: Participant, body: schemas.CloseIn | None = None):
    negotiation = service.cancel_negotiation(db, actor, negotiation_id, reason=body.reason if body else None)
    db.commit()
    return _present(actor, db, negotiation)
