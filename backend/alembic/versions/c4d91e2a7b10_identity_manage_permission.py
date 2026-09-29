"""identity manage permission

Revision ID: c4d91e2a7b10
Revises: a975cb9cba44
Create Date: 2026-09-29 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4d91e2a7b10"
down_revision: Union[str, Sequence[str], None] = "a975cb9cba44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO permissions (id, code, description) VALUES "
        "(gen_random_uuid(), 'identity.manage', 'Create and maintain SourceOne user accounts')"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r, permissions p "
        "WHERE r.code = 'platform_admin' AND p.code = 'identity.manage'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'identity.manage')")
    op.execute("DELETE FROM permissions WHERE code = 'identity.manage'")
