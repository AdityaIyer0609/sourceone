import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel, Money

VerificationStatus = Literal["unverified", "pending", "verified"]


class ServiceRegionIn(ApiModel):
    label: str = Field(min_length=1, max_length=64)
    pin_prefix: str | None = Field(default=None, min_length=3, max_length=3)


class ServiceRegionsIn(ApiModel):
    regions: list[ServiceRegionIn] = Field(max_length=12)


class VerificationIn(ApiModel):
    status: VerificationStatus


class ServiceRegionOut(ApiModel):
    label: str
    pin_prefix: str | None


class CountRateOut(ApiModel):
    """A rate is present only when the denominator is real stored rows. Otherwise percent is null."""

    available: bool
    note: str
    count: int
    total: int
    percent: str | None


class ResponseTimeOut(ApiModel):
    available: bool
    note: str
    sample_count: int
    average_hours: str | None


class SupplierPersonOut(ApiModel):
    name: str
    email: str | None


class SupplierProductOut(ApiModel):
    product_code: str
    name: str
    uom: str
    minimum_quantity: str
    maximum_quantity: str | None = None
    asking_price: Money
    availability: Literal["in_stock", "limited", "on_request"]


class SupplierQuoteOut(ApiModel):
    id: uuid.UUID
    reference: str
    product_name: str
    status: str
    latest_offer: Money | None
    updated_at: datetime


class SupplierOrderOut(ApiModel):
    id: uuid.UUID
    reference: str
    product_name: str
    status: str
    total_value: Money
    updated_at: datetime


class SupplierComparisonOut(ApiModel):
    basis: Literal["lane", "per_km"] | None
    freight: Money | None
    material: Money
    landed: Money | None
    factor: str | None
    adjusted: Money | None
    notes: list[str]
    place: int | None


class SupplierMatchOut(ApiModel):
    supplier_user_id: uuid.UUID
    supplier_name: str
    organisation: str
    organisation_id: uuid.UUID
    asking_price: Money
    minimum_quantity: str
    maximum_quantity: str | None = None
    uom: str
    availability: Literal["in_stock", "limited", "on_request"]
    origin_pin: str | None
    origin_label: str | None
    meets_minimum: bool
    freight_status: Literal["estimated", "on_request"]
    freight: Money | None
    freight_match: Literal["lane", "zone", "default"] | None
    reasons: list[str]
    response_time: ResponseTimeOut
    acceptance: CountRateOut
    order_cancellation: CountRateOut
    on_time_delivery: CountRateOut
    quality: CountRateOut
    comparison: SupplierComparisonOut


class SupplierMatchListOut(ApiModel):
    product_code: str
    quantity: str
    uom: str
    destination_pin: str
    matches: list[SupplierMatchOut]


class SupplierProfileOut(ApiModel):
    organisation_id: uuid.UUID
    name: str
    verification_status: VerificationStatus
    dispatch_pin: str | None
    dispatch_label: str | None
    service_regions: list[ServiceRegionOut]
    people: list[SupplierPersonOut]
    products: list[SupplierProductOut]
    response_time: ResponseTimeOut
    acceptance: CountRateOut
    order_cancellation: CountRateOut
    on_time_delivery: CountRateOut
    quality: CountRateOut
    quote_count: int
    order_count: int
    quotes: list[SupplierQuoteOut]
    orders: list[SupplierOrderOut]
    can_edit_regions: bool
    can_set_verification: bool
