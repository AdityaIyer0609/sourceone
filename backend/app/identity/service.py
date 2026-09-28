import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PermissionDenied
from app.models.identity import Permission, RolePermission, User, UserRole


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    permissions: frozenset[str]
    email: str | None = None

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, *permissions: str) -> None:
        """Raise unless the actor holds at least one of the given permissions."""
        if not any(p in self.permissions for p in permissions):
            raise PermissionDenied(
                f"Requires permission: {' or '.join(permissions)}",
                details={"required": list(permissions)},
            )


def get_active_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(
        select(User).where(User.email == email.strip().lower(), User.is_active.is_(True))
    )


def get_user_permissions(session: Session, user_id: uuid.UUID) -> frozenset[str]:
    rows = session.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    return frozenset(rows)


def actor_for(session: Session, user: User) -> Actor:
    return Actor(user_id=user.id, permissions=get_user_permissions(session, user.id), email=user.email)
