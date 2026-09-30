import uuid
from datetime import datetime
from typing import Literal

from app.schemas.pricing import ApiModel, Money
from app.schemas.supplier import CountRateOut, ResponseTimeOut


class SpendOut(ApiModel):
    currency: str
    amount: str


class SpendSliceOut(ApiModel):
    """Material total for one product or supplier. Cancelled orders are not included."""

    label: str
    currency: str
    amount: str
    order_count: int


class VarianceOut(ApiModel):
    """Agreed unit price minus the snapshot frozen on the negotiation. Absent when that snapshot is missing."""

    order_id: uuid.UUID
    order_number: str
    product_name: str
    agreed_unit_price: Money
    snapshot: Money
    unit_difference: Money
    material_difference: Money


class DeliveryOut(ApiModel):
    available: bool
    note: str
    on_time: int
    delivered: int
    percent: str | None = None


class MetricOut(ApiModel):
    available: bool
    note: str
    percent: str | None = None
    average_hours: str | None = None


class SupplierPanelOut(ApiModel):
    organisation_id: uuid.UUID
    organisation: str
    acceptance: MetricOut
    order_cancellation: MetricOut
    quality: MetricOut
    response_time: MetricOut


class AlertOut(ApiModel):
    kind: Literal["negotiation", "approval", "order"]
    id: uuid.UUID
    title: str
    detail: str


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
    open_requests: int
    pending_actions: int
    spend_basis: Literal["material"] = "material"
    spend: list[SpendOut]
    spend_by_product: list[SpendSliceOut]
    spend_by_supplier: list[SpendSliceOut]
    variance: list[VarianceOut]
    delivery: DeliveryOut
    suppliers: list[SupplierPanelOut]
    alerts: list[AlertOut]
    orders_by_status: dict[str, int]
    recent_orders: list[DashboardActivityOut]
    recent_negotiations: list[DashboardActivityOut]


class SupplierWorkOut(ApiModel):
    id: uuid.UUID
    title: str
    detail: str


class SupplierListingNoteOut(ApiModel):
    id: uuid.UUID
    product_code: str
    product_name: str
    availability: Literal["in_stock", "limited", "on_request"]
    is_active: bool
    asking_price: Money


class SupplierDocumentNoteOut(ApiModel):
    id: uuid.UUID
    order_id: uuid.UUID
    order_number: str
    document_type: str
    filename: str
    status: Literal["submitted", "accepted", "rejected"]


class SupplierPerformanceOut(ApiModel):
    acceptance: CountRateOut
    order_cancellation: CountRateOut
    on_time_delivery: CountRateOut
    quality: CountRateOut
    response_time: ResponseTimeOut


class SupplierDashboardOut(ApiModel):
    open_requests: int
    open_negotiations: int
    orders_to_confirm: int
    listings_to_review: int
    requests: list[SupplierWorkOut]
    negotiations: list[SupplierWorkOut]
    orders: list[SupplierWorkOut]
    listings: list[SupplierListingNoteOut]
    documents: list[SupplierDocumentNoteOut]
    performance: SupplierPerformanceOut
    alerts: list[AlertOut]
