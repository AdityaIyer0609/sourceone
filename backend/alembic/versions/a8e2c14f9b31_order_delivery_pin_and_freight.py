"""Store a delivery PIN and a freight estimate on an order, separate from the negotiated total.

Revision ID: a8e2c14f9b31
Revises: f1a6b3c84d10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8e2c14f9b31"
down_revision: Union[str, Sequence[str], None] = "f1a6b3c84d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("destination_pin", sa.String(length=6), nullable=True))
    op.add_column("orders", sa.Column("freight_status", sa.String(length=16), nullable=True))
    op.add_column("orders", sa.Column("freight_amount", sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column("orders", sa.Column("freight_match", sa.String(length=16), nullable=True))
    op.create_check_constraint(
        "ck_orders_destination_pin",
        "orders",
        "destination_pin IS NULL OR destination_pin ~ '^[1-9][0-9]{5}$'",
    )
    op.create_check_constraint(
        "ck_orders_freight_status",
        "orders",
        "freight_status IS NULL OR freight_status IN ('estimated', 'on_request')",
    )
    op.create_check_constraint(
        "ck_orders_freight_amount_matches_status",
        "orders",
        "freight_status IS NULL OR (freight_status = 'on_request' AND freight_amount IS NULL) OR (freight_status = 'estimated' AND freight_amount IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_freight_amount_matches_status", "orders", type_="check")
    op.drop_constraint("ck_orders_freight_status", "orders", type_="check")
    op.drop_constraint("ck_orders_destination_pin", "orders", type_="check")
    op.drop_column("orders", "freight_match")
    op.drop_column("orders", "freight_amount")
    op.drop_column("orders", "freight_status")
    op.drop_column("orders", "destination_pin")
