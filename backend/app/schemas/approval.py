import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel, Money


class ApprovalOut(ApiModel):
    """A decision record. The amount is the material total, not the payable estimate."""

    id: uuid.UUID
    status: Literal["pending", "approved", "declined", "deal_rejected"]
    negotiation_id: uuid.UUID
    negotiation_number: str
    product_name: str
    amount: Money
    threshold: Money
    destination_pin: str
    freight_basis: Literal["standard", "distance"]
    submitted_by: str
    decided_by: str | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class DecisionIn(ApiModel):
    note: str | None = Field(default=None, max_length=2000)


class CompanyUserOut(ApiModel):
    id: uuid.UUID
    full_name: str
    email: str
    roles: list[str]
    is_active: bool


class CompanyOut(ApiModel):
    id: uuid.UUID
    name: str
    threshold: Money | None
    users: list[CompanyUserOut] | None = None


class ThresholdIn(ApiModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=2)
    currency: str | None = None
