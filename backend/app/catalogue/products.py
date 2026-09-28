"""Buyer-facing product catalogue. Products point at rate series; they never hold or derive prices."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import CurrencyUnitMismatch, DuplicateProductCode, DuplicateProductMapping, NotFound
from app.models.catalogue import Product, ProductRateSeries
from app.models.pricing import RateSeries
from app.pricing.constants import SeriesVisibility


def create_product(
    session: Session,
    *,
    product_code: str,
    name: str,
    category: str,
    uom: str,
    subcategory: str | None = None,
    description: str | None = None,
    is_active: bool = True,
) -> Product:
    code = product_code.strip().upper()
    if session.scalar(select(Product.id).where(Product.product_code == code)) is not None:
        raise DuplicateProductCode(f"Product {code!r} already exists")
    product = Product(
        product_code=code, name=name, category=category, subcategory=subcategory,
        description=description, uom=uom.upper(), is_active=is_active,
    )
    session.add(product)
    session.flush()
    return product


def map_rate_series(
    session: Session, product: Product, series: RateSeries, *, display_order: int = 0, is_active: bool = True
) -> ProductRateSeries:
    existing = session.scalar(
        select(ProductRateSeries.id).where(
            ProductRateSeries.product_id == product.id, ProductRateSeries.rate_series_id == series.id
        )
    )
    if existing is not None:
        raise DuplicateProductMapping(
            f"Product {product.product_code!r} is already mapped to rate series {series.code!r}"
        )
    if series.unit != product.uom:
        raise CurrencyUnitMismatch(
            f"Rate series {series.code!r} is priced per {series.unit}, product is sold per {product.uom}"
        )
    link = ProductRateSeries(
        product_id=product.id, rate_series_id=series.id, display_order=display_order, is_active=is_active
    )
    session.add(link)
    session.flush()
    return link


def _catalogue_query():
    return (
        select(Product)
        .where(Product.is_active.is_(True))
        .options(
            selectinload(Product.series_links)
            .selectinload(ProductRateSeries.rate_series)
            .options(selectinload(RateSeries.grade), selectinload(RateSeries.market))
        )
    )


def list_active_products(session: Session, *, category: str | None = None) -> Sequence[Product]:
    stmt = _catalogue_query().order_by(Product.name, Product.product_code)
    if category:
        stmt = stmt.where(Product.category == category)
    return session.scalars(stmt).all()


def get_active_product(session: Session, product_code: str) -> Product:
    product = session.scalar(_catalogue_query().where(Product.product_code == product_code.upper()))
    if product is None:
        raise NotFound(f"Product {product_code!r} not found")
    return product


def buyer_series(product: Product) -> list[RateSeries]:
    """Active mappings to active, buyer-visible series, in display order (first is the default)."""
    return [
        link.rate_series
        for link in product.series_links
        if link.is_active
        and link.rate_series.is_active
        and link.rate_series.visibility == SeriesVisibility.SIGNED_IN_PLATFORM
    ]
