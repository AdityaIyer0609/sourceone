import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.catalogue import Product
from app.models.identity import User
from app.models.negotiation import QUANTITY, Negotiation, NegotiationVersion
from app.models.pricing import PRICE, _in
from app.orders.constants import OrderStatus
from app.pricing.constants import SUPPORTED_CURRENCIES, SUPPORTED_UNITS

ORDER_VALUE = Numeric(20, 2)


class Order(UUIDPrimaryKey, Timestamps, Base):
    """An order placed from an accepted negotiation. Commercial terms are a frozen snapshot of that acceptance."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(_in("status", OrderStatus), name="status"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
        CheckConstraint(_in("uom", SUPPORTED_UNITS), name="uom"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("agreed_unit_price > 0", name="agreed_unit_price_positive"),
        CheckConstraint("total_value = round(quantity * agreed_unit_price, 2)", name="total_matches_terms"),
        CheckConstraint("destination_pin IS NULL OR destination_pin ~ '^[1-9][0-9]{5}$'", name="destination_pin"),
        CheckConstraint("freight_status IS NULL OR freight_status IN ('estimated', 'on_request')", name="freight_status"),
        CheckConstraint(
            "freight_status IS NULL OR (freight_status = 'on_request' AND freight_amount IS NULL) OR (freight_status = 'estimated' AND freight_amount IS NOT NULL)",
            name="freight_amount_matches_status",
        ),
        CheckConstraint("buyer_user_id <> supplier_user_id", name="distinct_parties"),
        CheckConstraint("(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="cancelled_iff_cancelled_at"),
        Index("ix_orders_buyer_status", "buyer_user_id", "status"),
        Index("ix_orders_supplier_status", "supplier_user_id", "status"),
    )

    order_number: Mapped[str] = mapped_column(String(32), unique=True)
    # One order per accepted negotiation, including after cancellation.
    negotiation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("negotiations.id"), unique=True)
    negotiation_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("negotiation_versions.id"))
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    supplier_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    uom: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    agreed_unit_price: Mapped[Decimal] = mapped_column(PRICE)
    total_value: Mapped[Decimal] = mapped_column(ORDER_VALUE)
    destination_pin: Mapped[str | None] = mapped_column(String(6))
    freight_status: Mapped[str | None] = mapped_column(String(16))
    freight_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    freight_match: Mapped[str | None] = mapped_column(String(16))
    requirements: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    shipment_lr: Mapped[str | None] = mapped_column(String(40))
    shipment_transporter: Mapped[str | None] = mapped_column(String(80))
    shipment_vehicle: Mapped[str | None] = mapped_column(String(40))
    shipment_eta: Mapped[date | None] = mapped_column(Date)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    negotiation: Mapped[Negotiation] = relationship()
    negotiation_version: Mapped[NegotiationVersion] = relationship()
    buyer: Mapped[User] = relationship(foreign_keys=[buyer_user_id])
    supplier: Mapped[User] = relationship(foreign_keys=[supplier_user_id])
    product: Mapped[Product] = relationship()
    documents: Mapped[list["OrderDocument"]] = relationship(order_by="OrderDocument.created_at", viewonly=True)
    status_events: Mapped[list["OrderStatusEvent"]] = relationship(
        order_by="OrderStatusEvent.created_at", viewonly=True
    )


class OrderStatusEvent(UUIDPrimaryKey, Base):
    """One order status change. Append-only; the order's status is always its latest event's to_status."""

    __tablename__ = "order_status_events"
    __table_args__ = (
        CheckConstraint(_in("to_status", OrderStatus), name="to_status"),
        CheckConstraint(f"from_status IS NULL OR {_in('from_status', OrderStatus)}", name="from_status"),
        CheckConstraint("(from_status IS NULL) = (to_status = 'placed')", name="placed_is_first"),
        UniqueConstraint("order_id", "to_status", name="uq_order_status_events_order_to_status"),
        Index("ix_order_status_events_order_created", "order_id", "created_at"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    changed_by: Mapped[User] = relationship()
