from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import NotAuthenticated
from app.db.session import get_db
from app.identity.service import Actor, actor_for
from app.identity.tokens import read_user_id
from app.models.identity import User

DbSession = Annotated[Session, Depends(get_db)]


def get_current_actor(
    db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> Actor:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise NotAuthenticated("Sign in to continue.")
    user_id = read_user_id(authorization.split(" ", 1)[1].strip())
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.is_system:
        raise NotAuthenticated("Sign in to continue.")
    return actor_for(db, user)


CurrentActor = Annotated[Actor, Depends(get_current_actor)]


def require_any(*permissions: str) -> Callable[[Actor], Actor]:
    def dependency(actor: CurrentActor) -> Actor:
        actor.require(*permissions)
        return actor

    return dependency
