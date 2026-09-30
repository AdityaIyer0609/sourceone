import uuid
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel, Money

Availability = Literal["in_stock", "limited", "on_request"]


class ListingIn(ApiModel):
    product_code: str = Field(min_length=1, max_length=64)
    minimum_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    asking_price: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(min_length=3, max_length=3)
    availability: Availability
    is_active: bool = True


class ListingActiveIn(ApiModel):
    is_active: bool | None = None
    asking_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    minimum_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=3)
    availability: Availability | None = None


class ListingOut(ApiModel):
    id: uuid.UUID
    product_code: str
    product_name: str
    supplier_user_id: uuid.UUID
    supplier_name: str
    organisation: str
    organisation_id: uuid.UUID
    origin_pin: str | None
    origin_label: str | None
    uom: str
    minimum_quantity: str
    asking_price: Money
    availability: Availability
    is_active: bool
