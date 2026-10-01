import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel, Money

Availability = Literal["in_stock", "limited", "on_request"]
SubmissionStatus = Literal["pending", "accepted", "rejected"]


class SubmissionIn(ApiModel):
    proposed_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=64)
    subcategory: str | None = Field(default=None, max_length=64)
    description: str | None = None
    uom: str = Field(min_length=1, max_length=16)
    specifications: dict[str, str | None]
    asking_price: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(min_length=3, max_length=3)
    minimum_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    maximum_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=3)
    availability: Availability


class AcceptSubmissionIn(ApiModel):
    product_code: str | None = Field(default=None, max_length=64)


class RejectSubmissionIn(ApiModel):
    note: str = Field(min_length=1, max_length=500)


class SubmissionOut(ApiModel):
    id: uuid.UUID
    status: SubmissionStatus
    proposed_code: str
    product_code: str | None
    name: str
    category: str
    subcategory: str | None
    description: str | None
    uom: str
    specifications: dict[str, str]
    asking_price: Money
    minimum_quantity: str
    maximum_quantity: str | None
    availability: Availability
    supplier_user_id: uuid.UUID
    supplier_name: str
    organisation: str
    review_note: str | None
    created_at: datetime
