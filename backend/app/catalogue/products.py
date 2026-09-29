"""Buyer-facing product catalogue. Products point at rate series; they never hold or derive prices."""

from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.catalogue.specifications import clean_specifications
from app.core.errors import (
    CurrencyUnitMismatch,
    DuplicateProductCode,
    DuplicateProductMapping,
    NotFound,
    ProductInUse,
    ValidationFailed,
)
from app.models.catalogue import Product, ProductRateSeries
from app.models.negotiation import Negotiation
from app.models.order import Order
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
    specifications: dict | None = None,
) -> Product:
    code = product_code.strip().upper()
    if session.scalar(select(Product.id).where(Product.product_code == code)) is not None:
        raise DuplicateProductCode(f"Product {code!r} already exists")
    product = Product(
        product_code=code, name=name, category=category, subcategory=subcategory,
        description=description, uom=uom.upper(), is_active=is_active,
        specifications=clean_specifications(specifications) or None,
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


def list_active_products(
    session: Session, *, category: str | None = None, search: str | None = None,
) -> Sequence[Product]:
    """Buyer catalogue: active products only, using the same search as item master."""
    return list_catalogue(session, search=search, category=category, active=True)


def get_active_product(session: Session, product_code: str) -> Product:
    product = session.scalar(_catalogue_query().where(Product.product_code == product_code.upper()))
    if product is None:
        raise NotFound(f"Product {product_code!r} not found")
    return product


def _loaded():
    return select(Product).options(
        selectinload(Product.series_links)
        .selectinload(ProductRateSeries.rate_series)
        .options(selectinload(RateSeries.grade), selectinload(RateSeries.market))
    )


def list_catalogue(
    session: Session, *, search: str | None = None, category: str | None = None, active: bool | None = None,
) -> Sequence[Product]:
    """Every SourceOne product, including inactive ones. This is not the buyer catalogue."""
    stmt = _loaded().order_by(Product.product_code)
    if category:
        stmt = stmt.where(Product.category == category)
    if active is not None:
        stmt = stmt.where(Product.is_active.is_(active))
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(
            Product.product_code.ilike(like),
            Product.name.ilike(like),
            Product.category.ilike(like),
            Product.subcategory.ilike(like),
            Product.description.ilike(like),
        ))
    return session.scalars(stmt).all()


def get_product(session: Session, product_code: str) -> Product:
    product = session.scalar(_loaded().where(Product.product_code == product_code.strip().upper()))
    if product is None:
        raise NotFound(f"Product {product_code!r} not found", details={"productCode": product_code})
    return product


def update_product(
    session: Session, product_code: str, *, name: str, category: str,
    subcategory: str | None, description: str | None, specifications: dict | None = None,
) -> Product:
    product = get_product(session, product_code)
    product.name = name.strip()
    product.category = category.strip()
    product.subcategory = (subcategory or "").strip() or None
    product.description = (description or "").strip() or None
    if specifications is not None:
        product.specifications = clean_specifications(specifications) or None
    if not product.name or not product.category:
        raise ValidationFailed("Name and category are required")
    session.flush()
    return product


def set_product_active(session: Session, product_code: str, *, is_active: bool) -> Product:
    product = get_product(session, product_code)
    product.is_active = is_active
    session.flush()
    return product


def map_product_series(session: Session, product_code: str, series_code: str, *, display_order: int = 0) -> Product:
    product = get_product(session, product_code)
    series = session.scalar(select(RateSeries).where(RateSeries.code == series_code.strip()))
    if series is None:
        raise NotFound(f"Rate series {series_code!r} not found", details={"seriesCode": series_code})
    map_rate_series(session, product, series, display_order=display_order)
    session.expire(product, ["series_links"])
    return get_product(session, product.product_code)


def set_series_mapping_active(session: Session, product_code: str, series_code: str, *, is_active: bool) -> Product:
    product = get_product(session, product_code)
    link = next((item for item in product.series_links if item.rate_series.code == series_code), None)
    if link is None:
        raise NotFound(f"Product is not mapped to {series_code!r}", details={"seriesCode": series_code})
    link.is_active = is_active
    session.flush()
    return product


def refuse_delete(session: Session, product_code: str) -> None:
    """Products used by a negotiation or order are kept. Deactivate them instead."""
    product = get_product(session, product_code)
    referenced = session.scalar(select(Negotiation.id).where(Negotiation.product_id == product.id).limit(1))
    if referenced is None:
        referenced = session.scalar(select(Order.id).where(Order.product_id == product.id).limit(1))
    if referenced is not None:
        raise ProductInUse(
            "This product is used by a negotiation or order. Deactivate it instead of deleting it.",
            details={"productCode": product.product_code},
        )
    raise ProductInUse(
        "Deactivate the product instead of deleting it.",
        details={"productCode": product.product_code},
    )


def buyer_series(product: Product) -> list[RateSeries]:
    """Active mappings to active, buyer-visible series, in display order (first is the default)."""
    return [
        link.rate_series
        for link in product.series_links
        if link.is_active
        and link.rate_series.is_active
        and link.rate_series.visibility == SeriesVisibility.SIGNED_IN_PLATFORM
    ]
