import uuid
from decimal import Decimal

from pydantic import Field

from app.schemas.pricing import ApiModel


class DispatchIn(ApiModel):
    pin: str = Field(min_length=6, max_length=6)
    label: str = Field(min_length=1, max_length=64)


class LaneIn(ApiModel):
    destination_pin: str = Field(min_length=6, max_length=6)
    destination_label: str = Field(min_length=1, max_length=64)
    rate_per_kg: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(min_length=3, max_length=3)
    minimum_freight: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    is_active: bool = True


class KmRateIn(ApiModel):
    rate_per_km: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(min_length=3, max_length=3)
    minimum_freight: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    is_active: bool = True


class LaneOut(ApiModel):
    id: uuid.UUID
    origin_pin: str
    destination_pin: str
    destination_label: str
    rate_per_kg: str
    currency: str
    minimum_freight: str | None
    is_active: bool


class KmRateOut(ApiModel):
    id: uuid.UUID
    currency: str
    rate_per_km: str
    minimum_freight: str | None
    is_active: bool


class SupplierFreightOut(ApiModel):
    dispatch_pin: str | None
    dispatch_label: str | None
    lanes: list[LaneOut]
    km_rate: KmRateOut | None
