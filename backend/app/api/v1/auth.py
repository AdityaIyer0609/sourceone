"""Email and password sign-in. Permissions still come from the user's roles."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentActor, DbSession
from app.core.config import get_settings
from app.core.errors import NotAuthenticated
from app.identity.passwords import verify_password
from app.identity.tokens import issue_token
from app.models.identity import Role, User, UserRole
from app.schemas.auth import LoginIn, LoginOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(db: DbSession, user: User) -> UserOut:
    roles = list(db.scalars(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
        .order_by(Role.code)
    ).all())
    return UserOut(
        email=user.email,
        full_name=user.full_name,
        organisation=user.organisation.name,
        roles=roles,
    )


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: DbSession):
    user = db.scalar(
        select(User).where(User.email == body.email.strip().lower()).options(selectinload(User.organisation))
    )
    if user is None or user.is_system or not user.is_active or not verify_password(body.password, user.password_hash):
        raise NotAuthenticated("Email or password is incorrect.")
    settings = get_settings()
    return LoginOut(
        access_token=issue_token(user.id),
        expires_in=settings.auth_token_ttl_seconds,
        user=_user_out(db, user),
    )


@router.get("/me", response_model=UserOut)
def me(db: DbSession, actor: CurrentActor):
    user = db.scalar(select(User).where(User.id == actor.user_id).options(selectinload(User.organisation)))
    if user is None or not user.is_active or user.is_system:
        raise NotAuthenticated("Sign in to continue.")
    return _user_out(db, user)
