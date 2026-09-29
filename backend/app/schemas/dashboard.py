import uuid
from datetime import datetime
from typing import Literal

from app.schemas.pricing import ApiModel, Money


class SpendOut(ApiModel):
    currency: str
    amount: str


class DashboardActivityOut(ApiModel):
    kind: Literal["order", "negotiation"]
    id: uuid.UUID
    reference: str
    product_name: str
    counterparty: str
    quantity: str
    uom: str
    value: Money | None
    value_kind: Literal["order_total", "offer"]
    status: str
    updated_at: datetime
    can_reorder: bool


class DashboardOut(ApiModel):
    active_orders: int
    open_negotiations: int
    pending_actions: int
    spend: list[SpendOut]
    orders_by_status: dict[str, int]
    recent_orders: list[DashboardActivityOut]
    recent_negotiations: list[DashboardActivityOut]
