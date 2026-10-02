"""Remember when a listing's stock is fully sold.

Revision ID: n4e0f7b89d21
Revises: m3d9e6a78c10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n4e0f7b89d21"
down_revision: Union[str, Sequence[str], None] = "m3d9e6a78c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "supplier_listings",
        sa.Column("sold_out", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("supplier_listings", "sold_out")
