"""A supplier's own offer to sell a catalogue product. Asking prices are not ERP prices and are not published benchmark rows."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.catalogue import Product
from app.models.identity import User
from app.pricing.constants import SUPPORTED_CURRENCIES, SUPPORTED_UNITS

AVAILABILITY = ("in_stock", "limited", "on_request")


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(str(v)) for v in values)})"


class SupplierListing(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "supplier_listings"
    __table_args__ = (
        UniqueConstraint("supplier_user_id", "product_id", name="uq_supplier_listings_supplier_product"),
        CheckConstraint("minimum_quantity > 0", name="minimum_quantity_positive"),
        CheckConstraint("asking_price > 0", name="asking_price_positive"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
        CheckConstraint(_in("uom", SUPPORTED_UNITS), name="uom"),
        CheckConstraint(_in("availability", AVAILABILITY), name="availability"),
        CheckConstraint("maximum_quantity IS NULL OR maximum_quantity > 0", name="maximum_quantity_positive"),
        CheckConstraint(
            "maximum_quantity IS NULL OR maximum_quantity >= minimum_quantity",
            name="maximum_covers_minimum",
        ),
        CheckConstraint(
            "(availability = 'on_request') = (maximum_quantity IS NULL)",
            name="stock_only_when_selling",
        ),
    )

    supplier_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    uom: Mapped[str] = mapped_column(String(16))
    minimum_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    maximum_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    asking_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    availability: Mapped[str] = mapped_column(String(16))
    sold_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    supplier: Mapped[User] = relationship()
    product: Mapped[Product] = relationship()


class AskingPriceAverage(UUIDPrimaryKey, Base):
    """One point in the buyer-facing market rate: the average of active asking prices for a material."""

    __tablename__ = "asking_price_averages"
    __table_args__ = (
        CheckConstraint("average_price > 0", name="average_positive"),
        CheckConstraint("supplier_count > 0", name="supplier_count_positive"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    average_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    supplier_count: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
