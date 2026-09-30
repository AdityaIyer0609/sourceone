"""Supplier verification status and declared service regions.

Revision ID: c8f4e2a91b17
Revises: b3d9e1a74c20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8f4e2a91b17"
down_revision: Union[str, Sequence[str], None] = "b3d9e1a74c20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("verification_status", sa.String(length=16), server_default="unverified", nullable=False),
    )
    op.add_column(
        "organisations",
        sa.Column("service_regions", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )
    op.create_check_constraint(
        "ck_organisations_verification_status",
        "organisations",
        "verification_status IN ('unverified', 'pending', 'verified')",
    )
    op.create_check_constraint(
        "ck_organisations_profile_only_for_suppliers",
        "organisations",
        "org_type = 'supplier' OR (verification_status = 'unverified' AND service_regions = '[]'::jsonb)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_organisations_profile_only_for_suppliers", "organisations", type_="check")
    op.drop_constraint("ck_organisations_verification_status", "organisations", type_="check")
    op.drop_column("organisations", "service_regions")
    op.drop_column("organisations", "verification_status")
