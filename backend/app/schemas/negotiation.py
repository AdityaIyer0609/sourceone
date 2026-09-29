import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel, Money


class PartyOut(ApiModel):
    name: str
    organisation: str


class NegotiationProductOut(ApiModel):
    product_code: str
    name: str
    category: str


class BenchmarkSnapshotOut(ApiModel):
    """Reference value frozen when the negotiation was created. Never a price offered or agreed."""

    price_kind: Literal["sourceone_benchmark"] = "sourceone_benchmark"
    label: Literal["SourceOne benchmark (reference at start)"] = "SourceOne benchmark (reference at start)"
    state: Literal["fresh", "stale", "rate_on_request"]
    value: Money | None
    as_of_date: date | None
    series_code: str | None
    basis: str | None


class VersionOut(ApiModel):
    price_kind: Literal["offer"] = "offer"
    version_number: int
    offered_by: Literal["buyer", "supplier"]
    author: str
    offered_price: Money
    quantity: str
    uom: str
    message: str | None
    created_at: datetime


class NegotiatedPriceOut(ApiModel):
    price_kind: Literal["negotiated_price"] = "negotiated_price"
    version_number: int
    price: Money
    quantity: str
    uom: str


class AllowedActionsOut(ApiModel):
    offer: bool
    accept: bool
    reject: bool
    cancel: bool


class NegotiationOut(ApiModel):
    id: uuid.UUID
    negotiation_number: str
    status: Literal["draft", "open", "countered", "accepted", "rejected", "cancelled"]
    product: NegotiationProductOut
    quantity: str
    uom: str
    currency: str
    buyer: PartyOut
    supplier: PartyOut
    benchmark: BenchmarkSnapshotOut
    versions: list[VersionOut]
    negotiated: NegotiatedPriceOut | None
    awaiting: Literal["buyer", "supplier"] | None
    viewer_role: Literal["buyer", "supplier"]
    allowed_actions: AllowedActionsOut
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    closed_reason: str | None


class SupplierOptionOut(ApiModel):
    id: uuid.UUID
    name: str
    organisation: str


class CreateNegotiationIn(ApiModel):
    product_code: str = Field(min_length=1, max_length=64)
    series_code: str | None = None
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    offered_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    currency: str | None = None
    message: str | None = Field(default=None, max_length=2000)
    supplier_user_id: uuid.UUID | None = None


class OfferIn(ApiModel):
    offered_price: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=3)
    currency: str | None = None
    uom: str | None = None
    message: str | None = Field(default=None, max_length=2000)


class CloseIn(ApiModel):
    reason: str | None = Field(default=None, max_length=2000)
