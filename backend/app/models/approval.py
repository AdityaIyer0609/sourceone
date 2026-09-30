import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKey
from app.models.identity import Organisation, User
from app.models.negotiation import Negotiation


class OrderApproval(UUIDPrimaryKey, Base):
    """A request to place an order above the company material threshold. Not an order."""

    __tablename__ = "order_approvals"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'declined', 'deal_rejected')", name="status"),
        CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL AND decided_by_user_id IS NULL)",
            name="decision",
        ),
        CheckConstraint(
            "decided_by_user_id IS NULL OR decided_by_user_id <> submitted_by_user_id",
            name="four_eyes",
        ),
        CheckConstraint("amount > 0 AND threshold_amount > 0", name="amounts"),
        CheckConstraint("currency IN ('INR', 'USD') AND threshold_currency = currency", name="currency"),
        CheckConstraint("destination_pin ~ '^[1-9][0-9]{5}$'", name="destination_pin"),
        CheckConstraint("freight_basis IN ('standard', 'distance')", name="freight_basis"),
        Index(
            "uq_order_approvals_one_pending",
            "negotiation_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_order_approvals_organisation", "organisation_id", "status"),
    )

    negotiation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("negotiations.id"))
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    currency: Mapped[str] = mapped_column(String(3))
    threshold_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    threshold_currency: Mapped[str] = mapped_column(String(3))
    destination_pin: Mapped[str] = mapped_column(String(6))
    freight_basis: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    decision_note: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    negotiation: Mapped[Negotiation] = relationship()
    organisation: Mapped[Organisation] = relationship()
    submitted_by: Mapped[User] = relationship(foreign_keys=[submitted_by_user_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_user_id])
