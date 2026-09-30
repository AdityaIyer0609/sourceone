import uuid
from datetime import datetime

from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, false, func, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow
from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Organisation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "organisations"
    __table_args__ = (
        CheckConstraint("org_type IN ('platform', 'buyer', 'supplier')", name="org_type"),
        CheckConstraint(
            "verification_status IN ('unverified', 'pending', 'verified')",
            name="verification_status",
        ),
        CheckConstraint(
            "org_type = 'supplier' OR (verification_status = 'unverified' AND service_regions = '[]'::jsonb)",
            name="profile_only_for_suppliers",
        ),
        CheckConstraint(
            "(approval_threshold_amount IS NULL AND approval_threshold_currency IS NULL) "
            "OR (approval_threshold_amount > 0 AND approval_threshold_currency IN ('INR', 'USD'))",
            name="approval_threshold",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    org_type: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Dispatch origin for SourceOne freight estimates. Not an ERP location.
    dispatch_pin: Mapped[str | None] = mapped_column(String(6))
    dispatch_label: Mapped[str | None] = mapped_column(String(64))
    # Plenza verification. Not an ERP flag. Non-supplier orgs stay unverified.
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified", server_default="unverified")
    # Regions the supplier declares. Dispatch PIN stays the freight origin.
    service_regions: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    # Material total above this waits for another person in the company. Null means no approval.
    approval_threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    approval_threshold_currency: Mapped[str | None] = mapped_column(String(3))


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    # Null for service accounts, which never sign in. Never returned by the API.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Service accounts (e.g. the ingestion job) can author suggestions but never sign in.
    is_system: Mapped[bool] = mapped_column(default=False, server_default=false())

    organisation: Mapped[Organisation] = relationship()


class Role(UUIDPrimaryKey, Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))


class Permission(UUIDPrimaryKey, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
