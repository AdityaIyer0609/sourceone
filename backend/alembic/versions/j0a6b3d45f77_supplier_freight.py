"""Suppliers store their own freight lanes and a per-km fallback.

Revision ID: j0a6b3d45f77
Revises: i9f5a2c34e66
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j0a6b3d45f77"
down_revision: Union[str, Sequence[str], None] = "i9f5a2c34e66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supplier_freight_lanes",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("origin_pin", sa.String(length=6), nullable=False),
        sa.Column("destination_pin", sa.String(length=6), nullable=False),
        sa.Column("destination_label", sa.String(length=64), nullable=False),
        sa.Column("rate_per_kg", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("minimum_freight", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rate_per_kg > 0", name="rate_positive"),
        sa.CheckConstraint("minimum_freight IS NULL OR minimum_freight >= 0", name="minimum_freight_non_negative"),
        sa.CheckConstraint("currency IN ('INR', 'USD')", name="currency"),
        sa.CheckConstraint("origin_pin ~ '^[1-9][0-9]{5}$'", name="origin_pin"),
        sa.CheckConstraint("destination_pin ~ '^[1-9][0-9]{5}$'", name="destination_pin"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "origin_pin", "destination_pin", "currency", name="uq_supplier_freight_lane"),
    )
    op.create_index("ix_supplier_freight_lanes_organisation_id", "supplier_freight_lanes", ["organisation_id"])
    op.create_table(
        "supplier_freight_km_rates",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate_per_km", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("minimum_freight", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rate_per_km > 0", name="rate_positive"),
        sa.CheckConstraint("minimum_freight IS NULL OR minimum_freight >= 0", name="minimum_freight_non_negative"),
        sa.CheckConstraint("currency IN ('INR', 'USD')", name="currency"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "currency", name="uq_supplier_freight_km"),
    )
    op.create_index("ix_supplier_freight_km_rates_organisation_id", "supplier_freight_km_rates", ["organisation_id"])


def downgrade() -> None:
    op.drop_index("ix_supplier_freight_km_rates_organisation_id", table_name="supplier_freight_km_rates")
    op.drop_table("supplier_freight_km_rates")
    op.drop_index("ix_supplier_freight_lanes_organisation_id", table_name="supplier_freight_lanes")
    op.drop_table("supplier_freight_lanes")
