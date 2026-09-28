import uuid
from datetime import datetime
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
