import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.negotiation import PartyOut
from app.schemas.pricing import ApiModel, Money


class OrderProductOut(ApiModel):
    product_code: str
    name: str
    category: str


class AgreedPriceOut(ApiModel):
    """The accepted negotiation's unit price, frozen on the order. Not a benchmark."""

    price_kind: Literal["negotiated_price"] = "negotiated_price"
    unit_price: Money
    uom: str


class NegotiationRefOut(ApiModel):
    id: uuid.UUID
    negotiation_number: str
    accepted_version_number: int


class OrderActionsOut(ApiModel):
    cancel: bool


class OrderOut(ApiModel):
    id: uuid.UUID
    order_number: str
    status: Literal["placed", "confirmed", "processing", "ready", "dispatched", "delivered", "cancelled"]
    product: OrderProductOut
    quantity: str
    uom: str
    currency: str
    agreed_price: AgreedPriceOut
    total_value: Money
    negotiation: NegotiationRefOut
    buyer: PartyOut
    supplier: PartyOut
    viewer_role: Literal["buyer", "supplier"]
    allowed_actions: OrderActionsOut
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None
    cancel_reason: str | None


OrderStatusName = Literal["placed", "confirmed", "processing", "ready", "dispatched", "delivered", "cancelled"]


class TrackingStepOut(ApiModel):
    status: OrderStatusName
    label: str
    state: Literal["completed", "current", "pending"]
    at: datetime | None
    note: str | None
    changed_by: str | None


class StatusEventOut(ApiModel):
    from_status: OrderStatusName | None
    to_status: OrderStatusName
    changed_by: str
    changed_by_role: Literal["buyer", "supplier"]
    note: str | None
    created_at: datetime


class TrackingOut(ApiModel):
    order_id: uuid.UUID
    order_number: str
    status: OrderStatusName
    product: OrderProductOut
    quantity: str
    uom: str
    buyer: PartyOut
    supplier: PartyOut
    viewer_role: Literal["buyer", "supplier"]
    next_status: OrderStatusName | None
    can_progress: bool
    steps: list[TrackingStepOut]
    events: list[StatusEventOut]
    last_updated_at: datetime


class StatusChangeIn(ApiModel):
    to_status: OrderStatusName
    note: str | None = Field(default=None, max_length=2000)


class CancelOrderIn(ApiModel):
    reason: str | None = Field(default=None, max_length=2000)


class ReorderItemOut(ApiModel):
    order_id: uuid.UUID
    order_number: str
    order_status: OrderStatusName
    product_code: str
    product_name: str
    supplier_user_id: uuid.UUID
    supplier_name: str
    organisation: str
    quantity: str
    uom: str
    currency: str
    previous_price: Money
    ordered_at: datetime
    available: bool
    unavailable_reason: Literal["cancelled", "inactive_product", "inactive_supplier", "no_listing"] | None
    current_asking_price: Money | None
    current_benchmark: Money | None


class ReorderIn(ApiModel):
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    destination_pin: str | None = Field(default=None, min_length=6, max_length=6)


class ReorderOut(ApiModel):
    negotiation_id: uuid.UUID
    negotiation_number: str
    quantity: str
    uom: str
    offered_price: Money
    previous_price: Money
    current_benchmark: Money | None
    destination_pin: str | None
    freight_status: Literal["estimated", "on_request", "not_requested"]
    freight: Money | None
    note: str
