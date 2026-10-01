"""SourceOne freight rules. These are estimates owned by SourceOne, never copied from ERP.

Supplier lanes and per-km rates are that supplier's own estimate. They are not platform rules and not ERP freight.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint, true
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
        CheckConstraint("origin_pin ~ '^[1-9][0-9]{2}([0-9]{3})?$'", name="origin_pin"),
        CheckConstraint("destination_pin ~ '^[1-9][0-9]{2}([0-9]{3})?$'", name="destination_pin"),
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


class FreightDefault(UUIDPrimaryKey, Timestamps, Base):
    """Flat per-kg rate used only when no lane or PIN zone matches. Not a distance."""

    __tablename__ = "freight_defaults"
    __table_args__ = (
        CheckConstraint("rate_per_kg > 0", name="rate_positive"),
        CheckConstraint("minimum_freight IS NULL OR minimum_freight >= 0", name="minimum_freight_non_negative"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
    )

    currency: Mapped[str] = mapped_column(String(3), unique=True)
    rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    minimum_freight: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class PinCoordinate(UUIDPrimaryKey, Timestamps, Base):
    """Resolved PIN location. Stored so Geoapify is not called again for the same PIN."""

    __tablename__ = "pin_coordinates"
    __table_args__ = (
        CheckConstraint("pin ~ '^[1-9][0-9]{5}$'", name="pin"),
    )

    pin: Mapped[str] = mapped_column(String(6), unique=True)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))


class RoadDistance(UUIDPrimaryKey, Timestamps, Base):
    """Driving distance for one origin PIN to one destination PIN. Not a straight line."""

    __tablename__ = "road_distances"
    __table_args__ = (
        CheckConstraint("origin_pin ~ '^[1-9][0-9]{5}$'", name="origin_pin"),
        CheckConstraint("destination_pin ~ '^[1-9][0-9]{5}$'", name="destination_pin"),
        CheckConstraint("distance_km > 0", name="distance_positive"),
        UniqueConstraint("origin_pin", "destination_pin", name="uq_road_distances_pair"),
    )

    origin_pin: Mapped[str] = mapped_column(String(6))
    destination_pin: Mapped[str] = mapped_column(String(6))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    provider: Mapped[str] = mapped_column(String(32))


class FreightDistanceRate(UUIDPrimaryKey, Timestamps, Base):
    """₹ per road-km, used only when no saved lane matches and a road distance exists."""

    __tablename__ = "freight_distance_rates"
    __table_args__ = (
        CheckConstraint("rate_per_km > 0", name="rate_positive"),
        CheckConstraint("minimum_freight IS NULL OR minimum_freight >= 0", name="minimum_freight_non_negative"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
    )

    currency: Mapped[str] = mapped_column(String(3), unique=True)
    rate_per_km: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    minimum_freight: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class SupplierFreightLane(UUIDPrimaryKey, Timestamps, Base):
    """A supplier's saved rate per kg from their dispatch PIN to one destination. Estimate only."""

    __tablename__ = "supplier_freight_lanes"
    __table_args__ = (
        UniqueConstraint("organisation_id", "origin_pin", "destination_pin", "currency", name="uq_supplier_freight_lane"),
        CheckConstraint("rate_per_kg > 0", name="rate_positive"),
        CheckConstraint("minimum_freight IS NULL OR minimum_freight >= 0", name="minimum_freight_non_negative"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
        CheckConstraint("origin_pin ~ '^[1-9][0-9]{5}$'", name="origin_pin"),
        CheckConstraint("destination_pin ~ '^[1-9][0-9]{5}$'", name="destination_pin"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    origin_pin: Mapped[str] = mapped_column(String(6))
    destination_pin: Mapped[str] = mapped_column(String(6))
    destination_label: Mapped[str] = mapped_column(String(64))
    rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3))
    minimum_freight: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class SupplierFreightKmRate(UUIDPrimaryKey, Timestamps, Base):
    """Used only when no saved lane matches this destination and a road distance exists."""

    __tablename__ = "supplier_freight_km_rates"
    __table_args__ = (
        UniqueConstraint("organisation_id", "currency", name="uq_supplier_freight_km"),
        CheckConstraint("rate_per_km > 0", name="rate_positive"),
        CheckConstraint("minimum_freight IS NULL OR minimum_freight >= 0", name="minimum_freight_non_negative"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    rate_per_km: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    minimum_freight: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
