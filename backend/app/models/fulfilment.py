import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKey
from app.models.identity import User
from app.models.negotiation import Negotiation
from app.models.order import Order

DOCUMENT_TYPES = (
    "coa", "mtc", "test_certificate", "inspection_report", "invoice", "lr", "eway_bill", "packing_list", "pod",
)


class RequirementResponse(UUIDPrimaryKey, Base):
    """A supplier's answer to one frozen requirement. Not a live product specification."""

    __tablename__ = "requirement_responses"
    __table_args__ = (
        CheckConstraint("status IN ('met', 'not_met')", name="status"),
        UniqueConstraint("negotiation_id", "requirement_key", name="uq_requirement_responses_key"),
    )

    negotiation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("negotiations.id"))
    requirement_key: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(String(500))
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    negotiation: Mapped[Negotiation] = relationship()


class OrderDocument(UUIDPrimaryKey, Base):
    """A fulfilment file for one order. Catalogue product files stay on ProductDocument."""

    __tablename__ = "order_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('coa', 'mtc', 'test_certificate', 'inspection_report', 'invoice', 'lr', 'eway_bill', 'packing_list', 'pod')",
            name="document_type",
        ),
        CheckConstraint("status IN ('submitted', 'accepted', 'rejected')", name="status"),
        CheckConstraint("byte_size > 0", name="byte_size"),
        CheckConstraint(
            "(status = 'submitted') = (reviewed_at IS NULL AND reviewed_by_user_id IS NULL)",
            name="review",
        ),
        Index("ix_order_documents_order", "order_id"),
        UniqueConstraint("stored_name"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    document_type: Mapped[str] = mapped_column(String(32))
    stored_name: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship()
    uploaded_by: Mapped[User] = relationship(foreign_keys=[uploaded_by_user_id])
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_user_id])
