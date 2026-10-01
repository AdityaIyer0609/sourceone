"""Suppliers publish the freight used to compare them. It never becomes an order price."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.identity.service import Actor
from app.negotiation.constants import NegotiationPermission
from app.schemas.supplier_freight import DispatchIn, KmRateIn, LaneIn, SupplierFreightOut
from app.suppliers import freight as service

router = APIRouter(prefix="/supplier-freight", tags=["supplier-freight"])

Supplier = Annotated[Actor, Depends(require_any(NegotiationPermission.SUPPLY))]


def _amount(value) -> str | None:
    return None if value is None else f"{value:.4f}"


def _present(db: DbSession, actor: Actor) -> SupplierFreightOut:
    org = service.organisation_for(db, actor)
    rate = service.km_rate(db, org.id)
    return SupplierFreightOut(
        dispatch_pin=org.dispatch_pin,
        dispatch_label=org.dispatch_label,
        lanes=[
            {
                "id": row.id,
                "origin_pin": row.origin_pin,
                "destination_pin": row.destination_pin,
                "destination_label": row.destination_label,
                "rate_per_kg": f"{row.rate_per_kg:.4f}",
                "currency": row.currency,
                "minimum_freight": _amount(row.minimum_freight),
                "is_active": row.is_active,
            }
            for row in service.lanes(db, org.id)
        ],
        km_rate=None if rate is None else {
            "id": rate.id,
            "currency": rate.currency,
            "rate_per_km": f"{rate.rate_per_km:.4f}",
            "minimum_freight": _amount(rate.minimum_freight),
            "is_active": rate.is_active,
        },
    )


@router.get("", response_model=SupplierFreightOut)
def read_freight(db: DbSession, actor: Supplier):
    return _present(db, actor)


@router.put("/dispatch", response_model=SupplierFreightOut)
def save_dispatch(body: DispatchIn, db: DbSession, actor: Supplier):
    service.set_dispatch(db, actor, pin=body.pin, label=body.label)
    db.commit()
    return _present(db, actor)


@router.post("/lanes", response_model=SupplierFreightOut, status_code=201)
def create_lane(body: LaneIn, db: DbSession, actor: Supplier):
    service.save_lane(
        db, actor, destination_pin=body.destination_pin, destination_label=body.destination_label,
        rate_per_kg=body.rate_per_kg, currency=body.currency, minimum_freight=body.minimum_freight,
        is_active=body.is_active,
    )
    db.commit()
    return _present(db, actor)


@router.patch("/lanes/{lane_id}", response_model=SupplierFreightOut)
def update_lane(lane_id: uuid.UUID, body: LaneIn, db: DbSession, actor: Supplier):
    service.save_lane(
        db, actor, lane_id=lane_id, destination_pin=body.destination_pin, destination_label=body.destination_label,
        rate_per_kg=body.rate_per_kg, currency=body.currency, minimum_freight=body.minimum_freight,
        is_active=body.is_active,
    )
    db.commit()
    return _present(db, actor)


@router.delete("/lanes/{lane_id}", response_model=SupplierFreightOut)
def delete_lane(lane_id: uuid.UUID, db: DbSession, actor: Supplier):
    service.remove_lane(db, actor, lane_id)
    db.commit()
    return _present(db, actor)


@router.put("/km-rate", response_model=SupplierFreightOut)
def save_km_rate(body: KmRateIn, db: DbSession, actor: Supplier):
    service.save_km_rate(
        db, actor, rate_per_km=body.rate_per_km, currency=body.currency,
        minimum_freight=body.minimum_freight, is_active=body.is_active,
    )
    db.commit()
    return _present(db, actor)
