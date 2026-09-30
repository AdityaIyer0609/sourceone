"""Buyer-facing market rate is the average of supplier asking prices, with freight on the negotiation.

Revision ID: b3d9e1a74c20
Revises: a8e2c14f9b31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3d9e1a74c20"
down_revision: Union[str, Sequence[str], None] = "a8e2c14f9b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asking_price_averages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("supplier_count", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("average_price > 0", name="ck_asking_price_averages_average_positive"),
        sa.CheckConstraint("supplier_count > 0", name="ck_asking_price_averages_supplier_count_positive"),
        sa.CheckConstraint("currency IN ('INR', 'USD')", name="ck_asking_price_averages_currency"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_asking_price_averages_product_id_products"),
        sa.PrimaryKeyConstraint("id", name="pk_asking_price_averages"),
    )
    op.create_index(op.f("ix_asking_price_averages_product_id"), "asking_price_averages", ["product_id"])
    op.execute(
        """
        INSERT INTO asking_price_averages (id, product_id, currency, average_price, supplier_count, recorded_at)
        SELECT gen_random_uuid(), sl.product_id, sl.currency,
               round(avg(sl.asking_price), 4), count(*)::int, min(sl.created_at)
        FROM supplier_listings sl
        JOIN users u ON u.id = sl.supplier_user_id
        WHERE sl.is_active IS TRUE AND u.is_active IS TRUE AND u.is_system IS FALSE
        GROUP BY sl.product_id, sl.currency
        """
    )
    op.add_column("negotiations", sa.Column("destination_pin", sa.String(length=6), nullable=True))
    op.add_column("negotiations", sa.Column("freight_status", sa.String(length=16), nullable=True))
    op.add_column("negotiations", sa.Column("freight_amount", sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column("negotiations", sa.Column("freight_match", sa.String(length=16), nullable=True))
    op.add_column("negotiations", sa.Column("freight_basis", sa.String(length=16), nullable=True))
    op.create_check_constraint(
        "ck_negotiations_destination_pin",
        "negotiations",
        "destination_pin IS NULL OR destination_pin ~ '^[1-9][0-9]{5}$'",
    )
    op.create_check_constraint(
        "ck_negotiations_freight_status",
        "negotiations",
        "freight_status IS NULL OR freight_status IN ('estimated', 'on_request')",
    )
    op.create_check_constraint(
        "ck_negotiations_freight_basis",
        "negotiations",
        "freight_basis IS NULL OR freight_basis IN ('standard', 'distance')",
    )
    op.create_check_constraint(
        "ck_negotiations_freight_amount_matches_status",
        "negotiations",
        "(freight_status IS NULL AND freight_amount IS NULL) OR "
        "(freight_status = 'on_request' AND freight_amount IS NULL) OR "
        "(freight_status = 'estimated' AND freight_amount IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_negotiations_freight_amount_matches_status", "negotiations", type_="check")
    op.drop_constraint("ck_negotiations_freight_basis", "negotiations", type_="check")
    op.drop_constraint("ck_negotiations_freight_status", "negotiations", type_="check")
    op.drop_constraint("ck_negotiations_destination_pin", "negotiations", type_="check")
    op.drop_column("negotiations", "freight_basis")
    op.drop_column("negotiations", "freight_match")
    op.drop_column("negotiations", "freight_amount")
    op.drop_column("negotiations", "freight_status")
    op.drop_column("negotiations", "destination_pin")
    op.drop_index(op.f("ix_asking_price_averages_product_id"), table_name="asking_price_averages")
    op.drop_table("asking_price_averages")
