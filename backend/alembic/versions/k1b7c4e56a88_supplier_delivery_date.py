"""Supplier offers can state a delivery date. The buyer's required date stays on the negotiation.

Revision ID: k1b7c4e56a88
Revises: j0a6b3d45f77
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k1b7c4e56a88"
down_revision: Union[str, Sequence[str], None] = "j0a6b3d45f77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("negotiation_versions", sa.Column("delivery_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("negotiation_versions", "delivery_date")
