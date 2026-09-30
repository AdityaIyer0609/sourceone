"""Supplier profiles. Metrics come from Plenza negotiations and orders, never from ERP."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.identity.constants import IdentityPermission
from app.identity.service import Actor
from app.negotiation.constants import NegotiationPermission
from app.pricing.constants import PricingPermission
from app.schemas.supplier import ServiceRegionsIn, SupplierProfileOut, VerificationIn
from app.suppliers import service

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

Viewer = Annotated[
    Actor,
    Depends(require_any(NegotiationPermission.BUY, NegotiationPermission.SUPPLY, IdentityPermission.MANAGE, PricingPermission.VIEW)),
]


@router.get("/{organisation_id}", response_model=SupplierProfileOut)
def get_supplier(organisation_id: uuid.UUID, db: DbSession, actor: Viewer):
    return service.profile(db, actor, organisation_id)


@router.put("/{organisation_id}/service-regions", response_model=SupplierProfileOut)
def replace_regions(organisation_id: uuid.UUID, body: ServiceRegionsIn, db: DbSession, actor: Viewer):
    profile = service.set_regions(
        db, actor, organisation_id, [region.model_dump() for region in body.regions],
    )
    db.commit()
    return profile


@router.patch("/{organisation_id}/verification", response_model=SupplierProfileOut)
def update_verification(organisation_id: uuid.UUID, body: VerificationIn, db: DbSession, actor: Viewer):
    profile = service.set_verification(db, actor, organisation_id, body.status)
    db.commit()
    return profile
