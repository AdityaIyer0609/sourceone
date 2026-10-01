"""Suppliers propose a catalogue product. A pricing admin accepts or rejects it."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_any
from app.api.v1.pricing_presenters import money
from app.catalogue import submissions as service
from app.identity.service import Actor
from app.models.catalogue import ProductSubmission
from app.negotiation.constants import NegotiationPermission
from app.pricing.constants import PricingPermission
from app.schemas.submission import AcceptSubmissionIn, RejectSubmissionIn, SubmissionIn, SubmissionOut

router = APIRouter(tags=["product-submissions"])

Supplier = Annotated[Actor, Depends(require_any(NegotiationPermission.SUPPLY))]
Editor = Annotated[Actor, Depends(require_any(PricingPermission.EDIT, PricingPermission.CONFIGURE))]


def _out(row: ProductSubmission) -> SubmissionOut:
    price = money(row.asking_price, row.currency)
    assert price is not None
    return SubmissionOut(
        id=row.id,
        status=row.status,
        proposed_code=row.proposed_code,
        product_code=row.product.product_code if row.product is not None else None,
        name=row.name,
        category=row.category,
        subcategory=row.subcategory,
        description=row.description,
        uom=row.uom,
        specifications={str(key): str(value) for key, value in row.specifications.items()},
        asking_price=price,
        minimum_quantity=f"{row.minimum_quantity.normalize():f}",
        maximum_quantity=f"{row.maximum_quantity.normalize():f}" if row.maximum_quantity is not None else None,
        availability=row.availability,
        supplier_user_id=row.supplier_user_id,
        supplier_name=row.supplier.full_name,
        organisation=row.supplier.organisation.name,
        review_note=row.review_note,
        created_at=row.created_at,
    )


@router.post("/product-submissions", response_model=SubmissionOut, status_code=201)
def create_submission(body: SubmissionIn, db: DbSession, actor: Supplier):
    row = service.submit(
        db, actor, proposed_code=body.proposed_code, name=body.name, category=body.category,
        subcategory=body.subcategory, description=body.description, uom=body.uom,
        specifications=body.specifications, asking_price=body.asking_price, currency=body.currency,
        minimum_quantity=body.minimum_quantity, availability=body.availability,
        maximum_quantity=body.maximum_quantity,
    )
    db.commit()
    return _out(service.get(db, row.id))


@router.get("/product-submissions", response_model=list[SubmissionOut])
def list_own_submissions(db: DbSession, actor: Supplier):
    return [_out(row) for row in service.own(db, actor)]


@router.get("/admin/product-submissions", response_model=list[SubmissionOut])
def list_submissions(
    db: DbSession,
    _: Editor,
    status: Annotated[str, Query()] = "pending",
):
    return [_out(row) for row in service.queue(db, _, status=status)]


@router.post("/admin/product-submissions/{submission_id}/accept", response_model=SubmissionOut)
def accept_submission(submission_id: uuid.UUID, body: AcceptSubmissionIn, db: DbSession, actor: Editor):
    row = service.accept(db, actor, submission_id, product_code=body.product_code)
    db.commit()
    return _out(service.get(db, row.id))


@router.post("/admin/product-submissions/{submission_id}/reject", response_model=SubmissionOut)
def reject_submission(submission_id: uuid.UUID, body: RejectSubmissionIn, db: DbSession, actor: Editor):
    row = service.reject(db, actor, submission_id, note=body.note)
    db.commit()
    return _out(service.get(db, row.id))
