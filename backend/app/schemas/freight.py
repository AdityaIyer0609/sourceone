import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel, Money


class FreightRuleIn(ApiModel):
    origin_pin: str = Field(min_length=3, max_length=6)
    origin_label: str = Field(min_length=1, max_length=64)
    destination_pin: str = Field(min_length=3, max_length=6)
    destination_label: str = Field(min_length=1, max_length=64)
    rate_per_kg: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(min_length=3, max_length=3)
    minimum_freight: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    is_active: bool = True
    effective_from: date
    effective_to: date | None = None


class FreightRuleOut(ApiModel):
    id: uuid.UUID
    origin_pin: str
    origin_label: str
    destination_pin: str
    destination_label: str
    rate_per_kg: str
    rate_unit: Literal["KG"]
    currency: str
    minimum_freight: str | None
    is_active: bool
    effective_from: date
    effective_to: date | None


class FreightDefaultIn(ApiModel):
    currency: str = Field(min_length=3, max_length=3)
    rate_per_kg: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    minimum_freight: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    is_active: bool = True


class FreightDefaultOut(ApiModel):
    id: uuid.UUID
    currency: str
    rate_per_kg: str
    minimum_freight: str | None
    is_active: bool


class FreightEstimateIn(ApiModel):
    supplier_user_id: uuid.UUID
    product_code: str = Field(min_length=1, max_length=64)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    destination_pin: str = Field(min_length=6, max_length=6)
    include_distance: bool = False


class FreightDistanceRateIn(ApiModel):
    currency: str = Field(min_length=3, max_length=3)
    rate_per_km: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    minimum_freight: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    is_active: bool = True


class FreightDistanceRateOut(ApiModel):
    id: uuid.UUID
    currency: str
    rate_per_km: str
    minimum_freight: str | None
    is_active: bool


class FreightEstimateOut(ApiModel):
    supplier_user_id: uuid.UUID
    product_code: str
    quantity: str
    uom: str
    origin_pin: str | None
    origin_label: str | None
    destination_pin: str
    destination_label: str | None
    supplier_asking_price: Money
    material_value: Money
    freight_status: Literal["estimated", "on_request"]
    freight: Money | None
    minimum_freight_applied: bool
    landed_cost_per_unit: Money | None
    landed_value: Money | None
    rule_id: uuid.UUID | None
    match: Literal["lane", "zone", "default", "distance"] | None
    road_distance_km: str | None = None
    distance_source: Literal["geoapify", "cache"] | None = None
    distance_status: Literal["estimated", "on_request", "not_requested"] = "not_requested"
    distance_freight: Money | None = None
    distance_minimum_applied: bool = False
    distance_landed_per_unit: Money | None = None
    distance_landed_value: Money | None = None
    distance_rate_per_km: str | None = None
    distance_note: str | None = None
    note: str
