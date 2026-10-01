"""Limited listings store the quantity the supplier can spare.

Revision ID: i9f5a2c34e66
Revises: h8e4f1b23d55
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i9f5a2c34e66"
down_revision: Union[str, Sequence[str], None] = "h8e4f1b23d55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BACKFILL = """
UPDATE {table}
SET maximum_quantity = CASE
    WHEN minimum_quantity > 5000 THEN minimum_quantity
    ELSE 5000
END
WHERE availability = 'limited' AND maximum_quantity IS NULL
"""


def _limits(table: str) -> None:
    op.add_column(table, sa.Column("maximum_quantity", sa.Numeric(precision=18, scale=3), nullable=True))
    op.execute(_BACKFILL.format(table=table))
    op.create_check_constraint("maximum_quantity_positive", table, "maximum_quantity IS NULL OR maximum_quantity > 0")
    op.create_check_constraint(
        "maximum_covers_minimum", table, "maximum_quantity IS NULL OR maximum_quantity >= minimum_quantity",
    )
    op.create_check_constraint(
        "limited_has_maximum", table, "(availability = 'limited') = (maximum_quantity IS NOT NULL)",
    )


def upgrade() -> None:
    _limits("supplier_listings")
    _limits("product_submissions")


def downgrade() -> None:
    for table in ("product_submissions", "supplier_listings"):
        op.drop_constraint("limited_has_maximum", table, type_="check")
        op.drop_constraint("maximum_covers_minimum", table, type_="check")
        op.drop_constraint("maximum_quantity_positive", table, type_="check")
        op.drop_column(table, "maximum_quantity")
