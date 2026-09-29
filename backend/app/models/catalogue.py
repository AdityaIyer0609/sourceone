import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.pricing import RateSeries


class Producer(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "producers"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class Grade(UUIDPrimaryKey, Timestamps, Base):
    """A SourceOne grade/material. Producer grades map onto it via grade_equivalence."""

    __tablename__ = "grades"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    polymer: Mapped[str] = mapped_column(String(32))
    application: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class Market(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "markets"
    __table_args__ = (
        CheckConstraint("market_type IN ('domestic', 'import_origin')", name="market_type"),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    market_type: Mapped[str] = mapped_column(String(32))
    state: Mapped[str | None] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(2))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class ProducerGradeAlias(UUIDPrimaryKey, Timestamps, Base):
    """Spelling variants a source uses for a producer's own grade code."""

    __tablename__ = "producer_grade_aliases"
    __table_args__ = (UniqueConstraint("producer_id", "alias_normalized"),)

    producer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("producers.id"))
    alias: Mapped[str] = mapped_column(String(128))
    alias_normalized: Mapped[str] = mapped_column(String(128))
    producer_grade_code: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class GradeEquivalence(UUIDPrimaryKey, Timestamps, Base):
    """Business decision: which SourceOne grade a producer grade counts as."""

    __tablename__ = "grade_equivalence"
    __table_args__ = (UniqueConstraint("producer_id", "producer_grade_code"),)

    producer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("producers.id"))
    producer_grade_code: Mapped[str] = mapped_column(String(64))
    grade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grades.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class MarketAlias(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "market_aliases"

    alias: Mapped[str] = mapped_column(String(128))
    alias_normalized: Mapped[str] = mapped_column(String(128), unique=True)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("markets.id"), index=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class Product(UUIDPrimaryKey, Timestamps, Base):
    """Buyer-facing catalogue entity. Carries no price; pricing is reached through product_rate_series."""

    __tablename__ = "products"

    product_code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    uom: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # SourceOne catalogue attributes. Not copied from ERP. Missing keys mean "not specified".
    specifications: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    series_links: Mapped[list["ProductRateSeries"]] = relationship(
        back_populates="product", order_by="ProductRateSeries.display_order"
    )


class ProductRateSeries(UUIDPrimaryKey, Timestamps, Base):
    """Which benchmark rate series price a product, one per market/currency/basis context."""

    __tablename__ = "product_rate_series"
    __table_args__ = (UniqueConstraint("product_id", "rate_series_id", name="uq_product_rate_series_pair"),)

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    rate_series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rate_series.id"), index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    product: Mapped[Product] = relationship(back_populates="series_links")
    rate_series: Mapped["RateSeries"] = relationship()
