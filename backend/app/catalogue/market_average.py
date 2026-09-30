"""Buyer-facing market rate: the average of active supplier asking prices for one material.

Freight is not included. A new point is stored only when that average changes.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue import listings as catalogue_listings
from app.core.clock import utcnow
from app.models.catalogue import Product, ProductRateSeries
from app.models.listing import AskingPriceAverage
from app.pricing.read_model import PRICE_QUANTUM

STALE_AFTER_DAYS = 14


@dataclass(frozen=True)
class AveragePoint:
    at: datetime
    value: Decimal
    point_id: uuid.UUID


@dataclass(frozen=True)
class MarketView:
    """average: suppliers are listing. on_request: they were, and none are active now."""

    kind: str
    average: Decimal | None
    supplier_count: int
    previous: Decimal | None
    as_of: datetime | None
    points: tuple[AveragePoint, ...]
    spread_min: Decimal | None = None
    spread_max: Decimal | None = None


def _prices(session: Session, product_ids: list[uuid.UUID], currency: str) -> list[Decimal]:
    code = currency.upper()
    prices: list[Decimal] = []
    for product_id in product_ids:
        product = session.get(Product, product_id)
        if product is None or not product.is_active:
            continue
        prices.extend(row.asking_price for row in catalogue_listings.eligible_listings(session, product, currency=code))
    return prices


def _rows(session: Session, product_ids: list[uuid.UUID], currency: str) -> list[AskingPriceAverage]:
    if not product_ids:
        return []
    return list(
        session.scalars(
            select(AskingPriceAverage)
            .where(
                AskingPriceAverage.product_id.in_(product_ids),
                AskingPriceAverage.currency == currency.upper(),
            )
            .order_by(AskingPriceAverage.recorded_at, AskingPriceAverage.id)
        ).all()
    )


def product_ids_for_series(session: Session, series_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(ProductRateSeries.product_id).where(
                ProductRateSeries.rate_series_id == series_id,
                ProductRateSeries.is_active.is_(True),
            )
        ).all()
    )


def gap(offer: Decimal | None, reference: Decimal | None) -> Decimal | None:
    """Offer minus a stored reference. Missing when either side is missing."""
    if offer is None or reference is None:
        return None
    return (offer - reference).quantize(PRICE_QUANTUM)


def current_average(session: Session, product_id: uuid.UUID, currency: str) -> Decimal | None:
    prices = _prices(session, [product_id], currency)
    if not prices:
        return None
    return (sum(prices, Decimal(0)) / len(prices)).quantize(PRICE_QUANTUM)


def record(session: Session, product_id: uuid.UUID, currency: str, now: datetime | None = None) -> None:
    """Append a point when the active average or the supplier count changes."""
    now = now or utcnow()
    code = currency.upper()
    prices = _prices(session, [product_id], code)
    if not prices:
        return
    average = (sum(prices, Decimal(0)) / len(prices)).quantize(PRICE_QUANTUM)
    last = session.scalar(
        select(AskingPriceAverage)
        .where(AskingPriceAverage.product_id == product_id, AskingPriceAverage.currency == code)
        .order_by(AskingPriceAverage.recorded_at.desc())
    )
    if last is not None and last.average_price == average and last.supplier_count == len(prices):
        return
    session.add(
        AskingPriceAverage(
            product_id=product_id,
            currency=code,
            average_price=average,
            supplier_count=len(prices),
            recorded_at=now,
        )
    )
    session.flush()


def view(session: Session, product_ids: list[uuid.UUID], currency: str) -> MarketView | None:
    prices = _prices(session, product_ids, currency)
    rows = _rows(session, product_ids, currency)
    if not prices and not rows:
        return None
    points = tuple(AveragePoint(row.recorded_at, row.average_price, row.id) for row in rows)
    if not prices:
        return MarketView("on_request", None, 0, None, points[-1].at if points else None, points)
    average = (sum(prices, Decimal(0)) / len(prices)).quantize(PRICE_QUANTUM)
    previous = None
    if points and points[-1].value != average:
        previous = points[-1].value
    elif len(points) >= 2:
        previous = points[-2].value
    spread_min = min(prices) if len(prices) >= 2 else None
    spread_max = max(prices) if len(prices) >= 2 else None
    return MarketView(
        "average", average, len(prices), previous, points[-1].at if points else utcnow(), points,
        spread_min, spread_max,
    )
