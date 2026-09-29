import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base, UUIDPrimaryKey
from app.models.catalogue import Product
from app.models.identity import User
from app.models.pricing import _in


class ProductDocument(UUIDPrimaryKey, Base):
    """A file stored by SourceOne for one product. Inactive documents stay hidden from buyers."""

    __tablename__ = "product_documents"
    __table_args__ = (
        Index("ix_product_documents_product", "product_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(120))
    document_type: Mapped[str] = mapped_column(String(32))
    stored_name: Mapped[str] = mapped_column(String(64), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[Product] = relationship()
    uploaded_by: Mapped[User] = relationship()


class ProductQuestion(UUIDPrimaryKey, Base):
    """A buyer's question on one product. Status becomes answered when a listing supplier replies."""

    __tablename__ = "product_questions"
    __table_args__ = (
        CheckConstraint(_in("status", ("open", "answered")), name="status"),
        Index("ix_product_questions_product", "product_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product: Mapped[Product] = relationship()
    buyer: Mapped[User] = relationship()
    answers: Mapped[list["ProductAnswer"]] = relationship(back_populates="question", order_by="ProductAnswer.created_at")


class ProductAnswer(UUIDPrimaryKey, Base):
    __tablename__ = "product_answers"

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_questions.id"), index=True)
    supplier_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    question: Mapped[ProductQuestion] = relationship(back_populates="answers")
    supplier: Mapped[User] = relationship()
