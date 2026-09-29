"""SourceOne freight rules. These are estimates owned by SourceOne, never copied from ERP."""

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Numeric, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.pricing.constants import SUPPORTED_CURRENCIES

RATE_UNIT = "KG"


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(str(v)) for v in values)})"


class FreightRule(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "freight_rules"
    __table_args__ = (
        CheckConstraint("rate_per_kg > 0", name="rate_positive"),
        CheckConstraint("minimum_freight IS NULL OR minimum_freight >= 0", name="minimum_freight_non_negative"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_range"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
        CheckConstraint(f"rate_unit = '{RATE_UNIT}'", name="rate_unit"),
        CheckConstraint("origin_pin ~ '^[1-9][0-9]{5}$'", name="origin_pin"),
        CheckConstraint("destination_pin ~ '^[1-9][0-9]{5}$'", name="destination_pin"),
    )

    origin_pin: Mapped[str] = mapped_column(String(6), index=True)
    origin_label: Mapped[str] = mapped_column(String(64))
    destination_pin: Mapped[str] = mapped_column(String(6), index=True)
    destination_label: Mapped[str] = mapped_column(String(64))
    rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    rate_unit: Mapped[str] = mapped_column(String(16), default=RATE_UNIT)
    currency: Mapped[str] = mapped_column(String(3))
    minimum_freight: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
