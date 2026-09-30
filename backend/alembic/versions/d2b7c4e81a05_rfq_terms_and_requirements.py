"""Required date, payment terms, and a specification snapshot on a purchase request.

Revision ID: d2b7c4e81a05
Revises: c8f4e2a91b17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2b7c4e81a05"
down_revision: Union[str, Sequence[str], None] = "c8f4e2a91b17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("purchase_requests", sa.Column("freight_basis", sa.String(length=16), server_default="standard", nullable=False))
    op.add_column("purchase_requests", sa.Column("required_by", sa.Date(), nullable=True))
    op.add_column("purchase_requests", sa.Column("payment_terms", sa.String(length=120), nullable=True))
    op.add_column("purchase_requests", sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_check_constraint(
        "ck_purchase_requests_freight_basis",
        "purchase_requests",
        "freight_basis IN ('standard', 'distance')",
    )
    op.add_column("negotiations", sa.Column("required_by", sa.Date(), nullable=True))
    op.add_column("negotiations", sa.Column("payment_terms", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("negotiations", "payment_terms")
    op.drop_column("negotiations", "required_by")
    op.drop_constraint("ck_purchase_requests_freight_basis", "purchase_requests", type_="check")
    op.drop_column("purchase_requests", "requirements")
    op.drop_column("purchase_requests", "payment_terms")
    op.drop_column("purchase_requests", "required_by")
    op.drop_column("purchase_requests", "freight_basis")
