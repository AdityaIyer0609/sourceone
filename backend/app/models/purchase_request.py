import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.catalogue import Product
from app.models.identity import User
from app.models.negotiation import QUANTITY, Negotiation
from app.models.pricing import _in
from app.pricing.constants import SUPPORTED_UNITS
from app.purchase_requests.constants import RequestStatus


class PurchaseRequest(UUIDPrimaryKey, Timestamps, Base):
    """A buyer's request for one product. Sending it opens negotiations; it never creates an order."""

    __tablename__ = "purchase_requests"
    __table_args__ = (
        CheckConstraint(_in("status", RequestStatus), name="status"),
        CheckConstraint(_in("uom", SUPPORTED_UNITS), name="uom"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("destination_pin ~ '^[1-9][0-9]{5}$'", name="destination_pin"),
        CheckConstraint("freight_basis IN ('standard', 'distance')", name="freight_basis"),
        CheckConstraint("offered_price IS NULL OR offered_price > 0", name="offered_price_positive"),
        CheckConstraint("(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="cancelled_iff_cancelled_at"),
        Index("ix_purchase_requests_buyer_status", "buyer_user_id", "status"),
    )

    request_number: Mapped[str] = mapped_column(String(32), unique=True)
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    uom: Mapped[str] = mapped_column(String(16))
    destination_pin: Mapped[str] = mapped_column(String(6))
    freight_basis: Mapped[str] = mapped_column(String(16), default="standard", server_default="standard")
    required_by: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(String(120))
    # Product specifications at the time of the request. Null on older rows; never invented later.
    requirements: Mapped[list | None] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(Text)
    offered_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    status: Mapped[str] = mapped_column(String(32))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    buyer: Mapped[User] = relationship(foreign_keys=[buyer_user_id])
    product: Mapped[Product] = relationship()
    suppliers: Mapped[list["PurchaseRequestSupplier"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class PurchaseRequestSupplier(UUIDPrimaryKey, Base):
    """One eligible supplier asked on a purchase request, and the negotiation opened for them."""

    __tablename__ = "purchase_request_suppliers"
    __table_args__ = (
        UniqueConstraint("request_id", "supplier_user_id", name="uq_purchase_request_suppliers_request_supplier"),
        Index("ix_purchase_request_suppliers_supplier", "supplier_user_id"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_requests.id"))
    supplier_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    negotiation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("negotiations.id"), unique=True)

    request: Mapped[PurchaseRequest] = relationship(back_populates="suppliers")
    supplier: Mapped[User] = relationship(foreign_keys=[supplier_user_id])
    negotiation: Mapped[Negotiation | None] = relationship()
