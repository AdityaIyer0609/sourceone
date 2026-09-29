"""Product questions. A supplier can answer only when they have an active listing for the product."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.catalogue import listings as catalogue_listings
from app.catalogue import products as catalogue
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.identity.service import Actor
from app.models.identity import User
from app.models.product_content import ProductAnswer, ProductQuestion
from app.negotiation.constants import NegotiationPermission


def _body(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 2000:
        raise ValidationFailed("Enter a question or answer up to 2000 characters", details={"field": "body"})
    return cleaned


def _query(product_id: uuid.UUID):
    return (
        select(ProductQuestion)
        .where(ProductQuestion.product_id == product_id)
        .options(
            selectinload(ProductQuestion.buyer).selectinload(User.organisation),
            selectinload(ProductQuestion.answers).selectinload(ProductAnswer.supplier).selectinload(User.organisation),
        )
        .order_by(ProductQuestion.created_at)
    )


def list_questions(session: Session, product_code: str) -> list[ProductQuestion]:
    product = catalogue.get_active_product(session, product_code)
    return list(session.scalars(_query(product.id)).all())


def can_answer(session: Session, actor: Actor, product_code: str) -> bool:
    if not actor.has(NegotiationPermission.SUPPLY):
        return False
    product = catalogue.get_active_product(session, product_code)
    return any(row.supplier_user_id == actor.user_id for row in catalogue_listings.eligible_listings(session, product))


def ask(session: Session, actor: Actor, product_code: str, body: str) -> ProductQuestion:
    actor.require(NegotiationPermission.BUY)
    product = catalogue.get_active_product(session, product_code)
    question = ProductQuestion(
        product_id=product.id, buyer_user_id=actor.user_id, body=_body(body), status="open",
    )
    session.add(question)
    session.flush()
    return session.scalar(_query(product.id).where(ProductQuestion.id == question.id))


def answer(session: Session, actor: Actor, product_code: str, question_id: uuid.UUID, body: str) -> ProductQuestion:
    if not can_answer(session, actor, product_code):
        raise PermissionDenied("Only a supplier listing this product can answer")
    product = catalogue.get_active_product(session, product_code)
    question = session.scalar(_query(product.id).where(ProductQuestion.id == question_id))
    if question is None:
        raise NotFound("Question not found", details={"questionId": str(question_id)})
    session.add(ProductAnswer(question_id=question.id, supplier_user_id=actor.user_id, body=_body(body)))
    question.status = "answered"
    session.flush()
    session.expire(question)
    return session.scalar(_query(product.id).where(ProductQuestion.id == question.id))
