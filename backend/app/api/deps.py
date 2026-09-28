from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotAuthenticated
from app.db.session import get_db
from app.identity.service import Actor, actor_for, get_active_user_by_email

DbSession = Annotated[Session, Depends(get_db)]


def get_current_actor(
    db: DbSession, x_demo_user: Annotated[str | None, Header()] = None
) -> Actor:
    if not get_settings().demo_auth_enabled:
        raise NotAuthenticated("Sign-in is not configured for this environment.")
    if not x_demo_user:
        raise NotAuthenticated("Sign in to access SourceOne benchmarks.")
    user = get_active_user_by_email(db, x_demo_user)
    if user is None or user.is_system:
        raise NotAuthenticated("Unknown or inactive user.")
    return actor_for(db, user)


CurrentActor = Annotated[Actor, Depends(get_current_actor)]


def require_any(*permissions: str) -> Callable[[Actor], Actor]:
    def dependency(actor: CurrentActor) -> Actor:
        actor.require(*permissions)
        return actor

    return dependency
