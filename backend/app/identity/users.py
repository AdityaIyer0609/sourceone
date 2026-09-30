"""Platform-admin user management. Passwords are hashed and never returned."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import InvalidStateTransition, NotFound, ValidationFailed
from app.identity.constants import ROLES, IdentityPermission
from app.identity.passwords import hash_password
from app.identity.service import Actor
from app.models.identity import Organisation, Role, User, UserRole


def _roles(session: Session, user_id: uuid.UUID) -> list[str]:
    return list(session.scalars(
        select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id).order_by(Role.code)
    ).all())


def list_users(session: Session, actor: Actor) -> list[User]:
    actor.require(IdentityPermission.MANAGE)
    return list(session.scalars(
        select(User).options(selectinload(User.organisation)).order_by(User.email)
    ).all())


def _role(session: Session, code: str) -> Role:
    if code not in ROLES:
        raise ValidationFailed("Choose a SourceOne role", details={"role": code})
    role = session.scalar(select(Role).where(Role.code == code))
    if role is None:
        raise ValidationFailed("Choose a SourceOne role", details={"role": code})
    return role


def _organisation(session: Session, *, role: str, name: str) -> Organisation:
    if role in ("platform_admin", "pricing_admin"):
        org = session.scalar(select(Organisation).where(Organisation.org_type == "platform").limit(1))
        if org is None:
            raise ValidationFailed("No platform organisation is available for this role")
        return org
    base = "".join(ch for ch in name.upper() if ch.isalnum())[:24] or "ORG"
    code = base
    suffix = 1
    while session.scalar(select(Organisation.id).where(Organisation.code == code)) is not None:
        suffix += 1
        code = f"{base}-{suffix}"
    org = Organisation(code=code, name=name, org_type="supplier" if role == "supplier" else "buyer")
    session.add(org)
    session.flush()
    return org


def _active_platform_admins(session: Session) -> int:
    return session.scalar(
        select(func.count())
        .select_from(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == "platform_admin", User.is_active.is_(True), User.is_system.is_(False))
    ) or 0


def create_user(
    session: Session, actor: Actor, *, full_name: str, email: str, password: str, role: str,
    organisation_id: uuid.UUID | None = None,
) -> User:
    actor.require(IdentityPermission.MANAGE)
    name = " ".join(full_name.split())
    address = email.strip().lower()
    if not name or len(name) > 255:
        raise ValidationFailed("Name is required", details={"field": "fullName"})
    if not address or "@" not in address:
        raise ValidationFailed("A valid email is required", details={"field": "email"})
    if len(password) < 8:
        raise ValidationFailed("Password must be at least 8 characters", details={"field": "password"})
    if session.scalar(select(User.id).where(User.email == address)) is not None:
        raise ValidationFailed("Email is already in use", details={"field": "email"})
    chosen = _role(session, role)
    if organisation_id is not None:
        organisation = session.get(Organisation, organisation_id)
        if organisation is None:
            raise ValidationFailed("Company not found", details={"organisationId": str(organisation_id)})
        expected = "supplier" if role == "supplier" else "platform" if role in ("platform_admin", "pricing_admin") else "buyer"
        if organisation.org_type != expected:
            raise ValidationFailed("That company does not match this role", details={"organisationId": str(organisation_id)})
    else:
        organisation = _organisation(session, role=role, name=name)
    user = User(
        email=address, full_name=name, organisation_id=organisation.id,
        is_active=True, is_system=False, password_hash=hash_password(password),
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=chosen.id, assigned_by_id=actor.user_id))
    session.flush()
    return session.scalar(select(User).where(User.id == user.id).options(selectinload(User.organisation)))


def set_user_active(session: Session, actor: Actor, user_id: uuid.UUID, *, is_active: bool) -> User:
    actor.require(IdentityPermission.MANAGE)
    user = session.scalar(select(User).where(User.id == user_id).options(selectinload(User.organisation)))
    if user is None:
        raise NotFound("User not found", details={"userId": str(user_id)})
    if user.is_system:
        raise InvalidStateTransition("A system account cannot be activated or deactivated")
    if user.id == actor.user_id and not is_active:
        raise InvalidStateTransition("You cannot deactivate your own account")
    if not is_active and "platform_admin" in _roles(session, user.id) and _active_platform_admins(session) <= 1:
        raise InvalidStateTransition("The last platform admin must stay active")
    user.is_active = is_active
    session.flush()
    return user


def set_user_role(session: Session, actor: Actor, user_id: uuid.UUID, role: str) -> User:
    actor.require(IdentityPermission.MANAGE)
    user = session.scalar(select(User).where(User.id == user_id).options(selectinload(User.organisation)))
    if user is None:
        raise NotFound("User not found", details={"userId": str(user_id)})
    if user.is_system:
        raise InvalidStateTransition("A system account cannot change role")
    if user.id == actor.user_id:
        raise InvalidStateTransition("You cannot change your own role")
    current = _roles(session, user.id)
    chosen = _role(session, role)
    if "platform_admin" in current and role != "platform_admin" and _active_platform_admins(session) <= 1:
        raise InvalidStateTransition("The last platform admin must keep that role")
    for link in session.scalars(select(UserRole).where(UserRole.user_id == user.id)).all():
        session.delete(link)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=chosen.id, assigned_by_id=actor.user_id))
    session.flush()
    return user
