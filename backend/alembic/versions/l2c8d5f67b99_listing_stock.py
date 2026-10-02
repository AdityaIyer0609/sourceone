"""In stock and limited listings carry a sellable quantity. On request does not.

Revision ID: l2c8d5f67b99
Revises: k1b7c4e56a88
"""

from typing import Sequence, Union

from alembic import op

revision: str = "l2c8d5f67b99"
down_revision: Union[str, Sequence[str], None] = "k1b7c4e56a88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _upgrade(table: str) -> None:
    op.drop_constraint("limited_has_maximum", table, type_="check")
    op.execute(
        f"UPDATE {table} SET maximum_quantity = GREATEST(minimum_quantity, 20000) "
        "WHERE availability = 'in_stock' AND maximum_quantity IS NULL"
    )
    op.create_check_constraint(
        "stock_only_when_selling",
        table,
        "(availability = 'on_request') = (maximum_quantity IS NULL)",
    )


def _downgrade(table: str) -> None:
    op.drop_constraint("stock_only_when_selling", table, type_="check")
    op.execute(f"UPDATE {table} SET maximum_quantity = NULL WHERE availability = 'in_stock'")
    op.create_check_constraint(
        "limited_has_maximum",
        table,
        "(availability = 'limited') = (maximum_quantity IS NOT NULL)",
    )


def upgrade() -> None:
    _upgrade("supplier_listings")
    _upgrade("product_submissions")


def downgrade() -> None:
    _downgrade("product_submissions")
    _downgrade("supplier_listings")
