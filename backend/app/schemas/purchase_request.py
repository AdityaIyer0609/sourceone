import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.negotiation import RequirementResponseOut
from app.schemas.pricing import ApiModel, ChargeOut, Money, QuotePositionOut


class PurchaseRequestIn(ApiModel):
    product_code: str = Field(min_length=1, max_length=32)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    uom: str = Field(min_length=1, max_length=16)
    destination_pin: str = Field(min_length=6, max_length=6)
    freight_basis: Literal["standard", "distance"] = "standard"
    required_by: date | None = None
    payment_terms: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=2000)
    supplier_user_ids: list[uuid.UUID] = []


class SuppliersIn(ApiModel):
    supplier_user_ids: list[uuid.UUID] = Field(min_length=1)


class RequirementOut(ApiModel):
    key: str
    label: str
    value: str


class RequestSupplierOut(ApiModel):
    supplier_user_id: uuid.UUID
    supplier_name: str
    organisation: str
    organisation_id: uuid.UUID
    negotiation_id: uuid.UUID | None
    negotiation_number: str | None
    negotiation_status: str | None
    asking_price: Money | None
    latest_offer: Money | None
    material_value: Money | None
    freight_status: Literal["estimated", "on_request"]
    freight: Money | None
    landed_estimate: Money | None
    charges: ChargeOut | None
    quote: QuotePositionOut
    requirement_responses: list[RequirementResponseOut] = []


class PurchaseRequestOut(ApiModel):
    id: uuid.UUID
    request_number: str
    status: Literal["draft", "sent", "in_negotiation", "converted", "cancelled"]
    product_code: str
    product_name: str
    quantity: str
    uom: str
    destination_pin: str
    freight_basis: Literal["standard", "distance"]
    required_by: date | None
    payment_terms: str | None
    requirements: list[RequirementOut] | None
    message: str | None
    buyer_name: str
    buyer_organisation: str
    viewer_role: Literal["buyer", "supplier"]
    suppliers: list[RequestSupplierOut]
    can_edit_suppliers: bool
    can_send: bool
    can_cancel: bool
    created_at: datetime
