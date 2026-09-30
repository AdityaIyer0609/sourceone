"""Orders above a company material threshold wait here. Approving is what creates the order."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.clock import utcnow
from app.core.errors import FourEyesRequired, InvalidStateTransition, NotFound, PermissionDenied, ValidationFailed
from app.identity.constants import IdentityPermission
from app.identity.service import Actor
from app.models.approval import OrderApproval
from app.models.identity import Organisation, Role, User, UserRole
from app.models.negotiation import Negotiation
from app.negotiation.constants import NegotiationStatus
from app.orders.constants import OrderPermission
from app.orders.service import _insert_order
from app.negotiation.service import negotiated_version

def _user(session: Session, actor: Actor) -> User:
    user = session.get(User, actor.user_id)
    if user is None:
        raise PermissionDenied("This account cannot view company orders")
    return user


def list_approvals(session: Session, actor: Actor) -> list[OrderApproval]:
    actor.require(OrderPermission.APPROVE, OrderPermission.PLACE)
    user = _user(session, actor)
    return list(session.scalars(
        select(OrderApproval)
        .where(OrderApproval.organisation_id == user.organisation_id)
        .options(
            selectinload(OrderApproval.negotiation).selectinload(Negotiation.product),
            selectinload(OrderApproval.submitted_by),
            selectinload(OrderApproval.decided_by),
        )
        .order_by(OrderApproval.created_at.desc())
    ).all())


def _pending(session: Session, actor: Actor, approval_id: uuid.UUID) -> OrderApproval:
    actor.require(OrderPermission.APPROVE)
    user = _user(session, actor)
    approval = session.scalar(
        select(OrderApproval)
        .where(OrderApproval.id == approval_id, OrderApproval.organisation_id == user.organisation_id)
        .options(selectinload(OrderApproval.negotiation).selectinload(Negotiation.versions), selectinload(OrderApproval.negotiation).selectinload(Negotiation.product))
        .with_for_update()
    )
    if approval is None:
        raise NotFound("Approval request not found", details={"approvalId": str(approval_id)})
    if approval.status != "pending":
        raise InvalidStateTransition("This request has already been decided", details={"status": approval.status})
    if approval.submitted_by_user_id == actor.user_id:
        raise FourEyesRequired("You cannot decide an order you submitted")
    return approval


def _decide(approval: OrderApproval, actor: Actor, status: str, note: str | None, now: datetime) -> None:
    approval.status = status
    approval.decided_by_user_id = actor.user_id
    approval.decided_at = now
    approval.decision_note = (note or "").strip() or None


def approve(session: Session, actor: Actor, approval_id: uuid.UUID, *, now: datetime | None = None) -> OrderApproval:
    now = now or utcnow()
    approval = _pending(session, actor, approval_id)
    negotiation = approval.negotiation
    if negotiation.status != NegotiationStatus.ACCEPTED:
        raise InvalidStateTransition("The negotiation is no longer accepted", details={"negotiationStatus": negotiation.status})
    accepted = negotiated_version(negotiation)
    if accepted is None:
        raise InvalidStateTransition("The negotiation has no accepted offer")
    _insert_order(session, actor, negotiation, accepted, approval.destination_pin, approval.freight_basis, now)
    _decide(approval, actor, "approved", None, now)
    session.flush()
    return approval


def decline(session: Session, actor: Actor, approval_id: uuid.UUID, *, note: str | None = None, now: datetime | None = None) -> OrderApproval:
    """Leave the negotiation accepted. The buyer can submit again. No order is created."""
    now = now or utcnow()
    approval = _pending(session, actor, approval_id)
    _decide(approval, actor, "declined", note, now)
    session.flush()
    return approval


def reject_deal(session: Session, actor: Actor, approval_id: uuid.UUID, *, note: str | None = None, now: datetime | None = None) -> OrderApproval:
    """Cancel the accepted negotiation. This is separate from declining the approval."""
    now = now or utcnow()
    approval = _pending(session, actor, approval_id)
    negotiation = approval.negotiation
    if negotiation.status != NegotiationStatus.ACCEPTED:
        raise InvalidStateTransition("The negotiation is no longer accepted", details={"negotiationStatus": negotiation.status})
    negotiation.status = NegotiationStatus.CANCELLED
    negotiation.accepted_version_id = None
    negotiation.closed_by_user_id = actor.user_id
    negotiation.closed_reason = (note or "").strip() or "Approver rejected the deal"
    negotiation.updated_at = now
    _decide(approval, actor, "deal_rejected", note, now)
    session.flush()
    return approval


def company(session: Session, actor: Actor) -> tuple[Organisation, list[User] | None]:
    actor.require(OrderPermission.PLACE, OrderPermission.APPROVE, IdentityPermission.ORGANISATION, IdentityPermission.MANAGE)
    user = _user(session, actor)
    organisation = session.get(Organisation, user.organisation_id)
    if organisation is None:
        raise NotFound("Company not found")
    if not (actor.has(IdentityPermission.ORGANISATION) or actor.has(IdentityPermission.MANAGE)):
        return organisation, None
    users = list(session.scalars(
        select(User).where(User.organisation_id == organisation.id, User.is_system.is_(False)).order_by(User.full_name)
    ).all())
    return organisation, users


def roles_for(session: Session, user_id: uuid.UUID) -> list[str]:
    return list(session.scalars(
        select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id).order_by(Role.code)
    ).all())


def set_threshold(
    session: Session, actor: Actor, *, amount: Decimal | None, currency: str | None,
) -> Organisation:
    actor.require(IdentityPermission.ORGANISATION, IdentityPermission.MANAGE)
    user = _user(session, actor)
    organisation = session.get(Organisation, user.organisation_id)
    if organisation is None:
        raise NotFound("Company not found")
    if amount is None and currency is None:
        organisation.approval_threshold_amount = None
        organisation.approval_threshold_currency = None
    elif amount is None or currency is None:
        raise ValidationFailed("Set both the amount and the currency, or clear both")
    else:
        code = currency.upper()
        if code not in ("INR", "USD") or amount <= 0:
            raise ValidationFailed("The threshold must be a positive INR or USD amount")
        organisation.approval_threshold_amount = amount
        organisation.approval_threshold_currency = code
    session.flush()
    return organisation
