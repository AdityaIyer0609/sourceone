import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.catalogue import Product
from app.models.identity import User
from app.models.pricing import PRICE, RateSeries, _in
from app.negotiation.constants import BenchmarkSnapshotState, NegotiationStatus
from app.pricing.constants import SUPPORTED_CURRENCIES, SUPPORTED_UNITS

QUANTITY = Numeric(18, 3)


class Negotiation(UUIDPrimaryKey, Timestamps, Base):
    """A buyer/supplier price negotiation for one product. The benchmark is a frozen reference snapshot."""

    __tablename__ = "negotiations"
    __table_args__ = (
        CheckConstraint(_in("status", NegotiationStatus), name="status"),
        CheckConstraint(_in("benchmark_state", BenchmarkSnapshotState), name="benchmark_state"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
        CheckConstraint(_in("uom", SUPPORTED_UNITS), name="uom"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("buyer_user_id <> supplier_user_id", name="distinct_parties"),
        CheckConstraint(
            "(benchmark_state = 'rate_on_request') = (benchmark_rate_snapshot IS NULL)",
            name="snapshot_matches_state",
        ),
        CheckConstraint(
            "(status IN ('accepted', 'rejected', 'cancelled')) = (closed_at IS NOT NULL)",
            name="closed_iff_terminal",
        ),
        CheckConstraint("(status = 'accepted') = (accepted_version_id IS NOT NULL)", name="accepted_has_version"),
        Index("ix_negotiations_buyer_status", "buyer_user_id", "status"),
        Index("ix_negotiations_supplier_status", "supplier_user_id", "status"),
    )

    negotiation_number: Mapped[str] = mapped_column(String(32), unique=True)
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    supplier_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    rate_series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rate_series.id"))
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    uom: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))

    benchmark_state: Mapped[str] = mapped_column(String(16))
    benchmark_rate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("benchmark_rates.id"))
    benchmark_rate_snapshot: Mapped[Decimal | None] = mapped_column(PRICE)
    benchmark_as_of: Mapped[date | None] = mapped_column(Date)
    benchmark_series_code: Mapped[str | None] = mapped_column(String(160))
    benchmark_basis: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16))
    accepted_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("negotiation_versions.id", use_alter=True)
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_reason: Mapped[str | None] = mapped_column(Text)

    buyer: Mapped[User] = relationship(foreign_keys=[buyer_user_id])
    supplier: Mapped[User] = relationship(foreign_keys=[supplier_user_id])
    product: Mapped[Product] = relationship()
    rate_series: Mapped[RateSeries | None] = relationship()
    versions: Mapped[list["NegotiationVersion"]] = relationship(
        back_populates="negotiation",
        order_by="NegotiationVersion.version_number",
        foreign_keys="NegotiationVersion.negotiation_id",
    )


class NegotiationVersion(UUIDPrimaryKey, Base):
    """One offer or counter-offer. Append-only: a database trigger rejects updates and deletes."""

    __tablename__ = "negotiation_versions"
    __table_args__ = (
        UniqueConstraint("negotiation_id", "version_number", name="uq_negotiation_versions_number"),
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint("offered_price > 0", name="offered_price_positive"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(_in("currency", SUPPORTED_CURRENCIES), name="currency"),
        CheckConstraint(_in("uom", SUPPORTED_UNITS), name="uom"),
    )

    negotiation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("negotiations.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    offered_price: Mapped[Decimal] = mapped_column(PRICE)
    currency: Mapped[str] = mapped_column(String(3))
    quantity: Mapped[Decimal] = mapped_column(QUANTITY)
    uom: Mapped[str] = mapped_column(String(16))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    negotiation: Mapped[Negotiation] = relationship(back_populates="versions", foreign_keys=[negotiation_id])
    created_by: Mapped[User] = relationship()
