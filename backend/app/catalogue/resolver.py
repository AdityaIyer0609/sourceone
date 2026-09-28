"""Read-only lookups over catalogue reference data. Pricing consumes these; it never defines them."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.catalogue import (
    Grade,
    GradeEquivalence,
    Market,
    MarketAlias,
    Producer,
    ProducerGradeAlias,
)


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").upper().split())


@dataclass(frozen=True)
class GradeResolution:
    grade: Grade
    alias: ProducerGradeAlias
    equivalence: GradeEquivalence


@dataclass(frozen=True)
class MarketResolution:
    market: Market
    alias: MarketAlias


def resolve_producer(session: Session, raw_name: str | None) -> Producer | None:
    key = normalize_text(raw_name)
    if not key:
        return None
    return session.scalar(
        select(Producer).where(
            Producer.is_active.is_(True),
            or_(func.upper(Producer.name) == key, func.upper(Producer.code) == key),
        )
    )


def resolve_grade(
    session: Session, producer_id: uuid.UUID, raw_grade: str | None
) -> GradeResolution | None:
    key = normalize_text(raw_grade)
    if not key:
        return None
    alias = session.scalar(
        select(ProducerGradeAlias).where(
            ProducerGradeAlias.producer_id == producer_id,
            ProducerGradeAlias.alias_normalized == key,
            ProducerGradeAlias.is_active.is_(True),
        )
    )
    if alias is None:
        return None
    equivalence = session.scalar(
        select(GradeEquivalence).where(
            GradeEquivalence.producer_id == producer_id,
            GradeEquivalence.producer_grade_code == alias.producer_grade_code,
            GradeEquivalence.is_active.is_(True),
        )
    )
    if equivalence is None:
        return None
    grade = session.get(Grade, equivalence.grade_id)
    if grade is None or not grade.is_active:
        return None
    return GradeResolution(grade=grade, alias=alias, equivalence=equivalence)


def resolve_market(session: Session, raw_market: str | None) -> MarketResolution | None:
    key = normalize_text(raw_market)
    if not key:
        return None
    alias = session.scalar(
        select(MarketAlias).where(
            MarketAlias.alias_normalized == key, MarketAlias.is_active.is_(True)
        )
    )
    if alias is None:
        return None
    market = session.get(Market, alias.market_id)
    if market is None or not market.is_active:
        return None
    return MarketResolution(market=market, alias=alias)
