"""The buyer's price on a purchase request.

Revision ID: m3d9e6a78c10
Revises: l2c8d5f67b99
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m3d9e6a78c10"
down_revision: Union[str, Sequence[str], None] = "l2c8d5f67b99"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("purchase_requests", sa.Column("offered_price", sa.Numeric(18, 4), nullable=True))
    op.create_check_constraint(
        "offered_price_positive",
        "purchase_requests",
        "offered_price IS NULL OR offered_price > 0",
    )


def downgrade() -> None:
    op.drop_constraint("offered_price_positive", "purchase_requests", type_="check")
    op.drop_column("purchase_requests", "offered_price")
