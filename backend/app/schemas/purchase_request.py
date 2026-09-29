import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel, Money


class PurchaseRequestIn(ApiModel):
    product_code: str = Field(min_length=1, max_length=32)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    uom: str = Field(min_length=1, max_length=16)
    destination_pin: str = Field(min_length=6, max_length=6)
    message: str | None = Field(default=None, max_length=2000)
    supplier_user_ids: list[uuid.UUID] = []


class SuppliersIn(ApiModel):
    supplier_user_ids: list[uuid.UUID] = Field(min_length=1)


class RequestSupplierOut(ApiModel):
    supplier_user_id: uuid.UUID
    supplier_name: str
    organisation: str
    negotiation_id: uuid.UUID | None
    negotiation_number: str | None
    negotiation_status: str | None
    asking_price: Money | None
    freight_status: Literal["estimated", "on_request"]
    freight: Money | None


class PurchaseRequestOut(ApiModel):
    id: uuid.UUID
    request_number: str
    status: Literal["draft", "sent", "in_negotiation", "converted", "cancelled"]
    product_code: str
    product_name: str
    quantity: str
    uom: str
    destination_pin: str
    message: str | None
    buyer_name: str
    buyer_organisation: str
    viewer_role: Literal["buyer", "supplier"]
    suppliers: list[RequestSupplierOut]
    can_edit_suppliers: bool
    can_send: bool
    can_cancel: bool
    created_at: datetime
