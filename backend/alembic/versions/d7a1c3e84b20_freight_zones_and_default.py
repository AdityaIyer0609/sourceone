"""Freight PIN zones and a per-currency default rate.

Revision ID: d7a1c3e84b20
Revises: c4d91e2a7b10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7a1c3e84b20"
down_revision: Union[str, Sequence[str], None] = "c4d91e2a7b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ZONE = r"^[1-9][0-9]{2}([0-9]{3})?$"
PIN = r"^[1-9][0-9]{5}$"


def upgrade() -> None:
    op.execute("ALTER TABLE freight_rules DROP CONSTRAINT ck_freight_rules_origin_pin")
    op.execute("ALTER TABLE freight_rules DROP CONSTRAINT ck_freight_rules_destination_pin")
    op.execute(f"ALTER TABLE freight_rules ADD CONSTRAINT ck_freight_rules_origin_pin CHECK (origin_pin ~ '{ZONE}')")
    op.execute(f"ALTER TABLE freight_rules ADD CONSTRAINT ck_freight_rules_destination_pin CHECK (destination_pin ~ '{ZONE}')")
    op.create_table(
        "freight_defaults",
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate_per_kg", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("minimum_freight", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("currency IN ('INR', 'USD')", name="ck_freight_defaults_currency"),
        sa.CheckConstraint("rate_per_kg > 0", name="ck_freight_defaults_rate_positive"),
        sa.CheckConstraint("minimum_freight IS NULL OR minimum_freight >= 0", name="ck_freight_defaults_minimum_freight_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_freight_defaults"),
        sa.UniqueConstraint("currency", name="uq_freight_defaults_currency"),
    )


def downgrade() -> None:
    op.drop_table("freight_defaults")
    op.execute("ALTER TABLE freight_rules DROP CONSTRAINT ck_freight_rules_origin_pin")
    op.execute("ALTER TABLE freight_rules DROP CONSTRAINT ck_freight_rules_destination_pin")
    op.execute(f"ALTER TABLE freight_rules ADD CONSTRAINT ck_freight_rules_origin_pin CHECK (origin_pin ~ '{PIN}')")
    op.execute(f"ALTER TABLE freight_rules ADD CONSTRAINT ck_freight_rules_destination_pin CHECK (destination_pin ~ '{PIN}')")
