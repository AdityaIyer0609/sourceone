"""Cache PIN coordinates and road distance, plus a per-km freight rate.

Revision ID: e4c8a91b6d02
Revises: d7a1c3e84b20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4c8a91b6d02"
down_revision: Union[str, Sequence[str], None] = "d7a1c3e84b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PIN = r"^[1-9][0-9]{5}$"


def upgrade() -> None:
    op.create_table(
        "pin_coordinates",
        sa.Column("pin", sa.String(length=6), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"pin ~ '{PIN}'", name="ck_pin_coordinates_pin"),
        sa.PrimaryKeyConstraint("id", name="pk_pin_coordinates"),
        sa.UniqueConstraint("pin", name="uq_pin_coordinates_pin"),
    )
    op.create_table(
        "road_distances",
        sa.Column("origin_pin", sa.String(length=6), nullable=False),
        sa.Column("destination_pin", sa.String(length=6), nullable=False),
        sa.Column("distance_km", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"origin_pin ~ '{PIN}'", name="ck_road_distances_origin_pin"),
        sa.CheckConstraint(f"destination_pin ~ '{PIN}'", name="ck_road_distances_destination_pin"),
        sa.CheckConstraint("distance_km > 0", name="ck_road_distances_distance_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_road_distances"),
        sa.UniqueConstraint("origin_pin", "destination_pin", name="uq_road_distances_pair"),
    )
    op.create_table(
        "freight_distance_rates",
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate_per_km", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("minimum_freight", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("currency IN ('INR', 'USD')", name="ck_freight_distance_rates_currency"),
        sa.CheckConstraint("rate_per_km > 0", name="ck_freight_distance_rates_rate_positive"),
        sa.CheckConstraint(
            "minimum_freight IS NULL OR minimum_freight >= 0",
            name="ck_freight_distance_rates_minimum_freight_non_negative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_freight_distance_rates"),
        sa.UniqueConstraint("currency", name="uq_freight_distance_rates_currency"),
    )


def downgrade() -> None:
    op.drop_table("freight_distance_rates")
    op.drop_table("road_distances")
    op.drop_table("pin_coordinates")
