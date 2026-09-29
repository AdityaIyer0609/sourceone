"""Platform-admin user management. Password hashes are never included in a response."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.identity.constants import IdentityPermission
from app.identity.service import Actor
from app.identity.users import _roles, create_user, list_users, set_user_active, set_user_role
from app.models.identity import User
from app.schemas.admin_user import AdminUserIn, AdminUserOut, UserActiveIn, UserRoleIn

router = APIRouter(prefix="/admin/users", tags=["users"])

Manager = Annotated[Actor, Depends(require_any(IdentityPermission.MANAGE))]


def _present(db: DbSession, user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        organisation=user.organisation.name,
        roles=_roles(db, user.id),
        is_active=user.is_active,
        is_system=user.is_system,
    )


@router.get("", response_model=list[AdminUserOut])
def get_users(db: DbSession, actor: Manager):
    return [_present(db, user) for user in list_users(db, actor)]


@router.post("", response_model=AdminUserOut, status_code=201)
def post_user(body: AdminUserIn, db: DbSession, actor: Manager):
    user = create_user(db, actor, full_name=body.full_name, email=body.email, password=body.password, role=body.role)
    db.commit()
    return _present(db, user)


@router.post("/{user_id}/active", response_model=AdminUserOut)
def post_active(user_id: uuid.UUID, body: UserActiveIn, db: DbSession, actor: Manager):
    user = set_user_active(db, actor, user_id, is_active=body.is_active)
    db.commit()
    return _present(db, user)


@router.post("/{user_id}/role", response_model=AdminUserOut)
def post_role(user_id: uuid.UUID, body: UserRoleIn, db: DbSession, actor: Manager):
    user = set_user_role(db, actor, user_id, body.role)
    db.commit()
    return _present(db, user)
