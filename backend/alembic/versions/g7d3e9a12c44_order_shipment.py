"""Shipment facts on the order, and one in-transit step after dispatch.

Revision ID: g7d3e9a12c44
Revises: f6c2d8e41a90
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g7d3e9a12c44"
down_revision: Union[str, Sequence[str], None] = "f6c2d8e41a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = "'placed', 'confirmed', 'processing', 'ready', 'dispatched', 'in_transit', 'delivered', 'cancelled'"
PREVIOUS_STATUSES = "'placed', 'confirmed', 'processing', 'ready', 'dispatched', 'delivered', 'cancelled'"

ORDERS_GUARD = """
CREATE OR REPLACE FUNCTION orders_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'order % cannot be deleted', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status IN ('delivered', 'cancelled') THEN
        RAISE EXCEPTION 'order % is % and is final', OLD.id, OLD.status USING ERRCODE = 'check_violation';
    END IF;
    IF (NEW.order_number, NEW.negotiation_id, NEW.negotiation_version_id, NEW.buyer_user_id, NEW.supplier_user_id,
        NEW.product_id, NEW.quantity, NEW.uom, NEW.currency, NEW.agreed_unit_price, NEW.total_value, NEW.created_at,
        NEW.requirements)
       IS DISTINCT FROM
       (OLD.order_number, OLD.negotiation_id, OLD.negotiation_version_id, OLD.buyer_user_id, OLD.supplier_user_id,
        OLD.product_id, OLD.quantity, OLD.uom, OLD.currency, OLD.agreed_unit_price, OLD.total_value, OLD.created_at,
        OLD.requirements) THEN
        RAISE EXCEPTION 'order % terms are immutable', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        (OLD.status = 'placed' AND NEW.status IN ('confirmed', 'cancelled')) OR
        (OLD.status = 'confirmed' AND NEW.status IN ('processing', 'cancelled')) OR
        (OLD.status = 'processing' AND NEW.status = 'ready') OR
        (OLD.status = 'ready' AND NEW.status = 'dispatched') OR
        (OLD.status = 'dispatched' AND NEW.status = 'in_transit') OR
        (OLD.status = 'in_transit' AND NEW.status = 'delivered')
    ) THEN
        RAISE EXCEPTION 'order % cannot move from % to %', OLD.id, OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
"""

PREVIOUS_GUARD = """
CREATE OR REPLACE FUNCTION orders_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'order % cannot be deleted', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status IN ('delivered', 'cancelled') THEN
        RAISE EXCEPTION 'order % is % and is final', OLD.id, OLD.status USING ERRCODE = 'check_violation';
    END IF;
    IF (NEW.order_number, NEW.negotiation_id, NEW.negotiation_version_id, NEW.buyer_user_id, NEW.supplier_user_id,
        NEW.product_id, NEW.quantity, NEW.uom, NEW.currency, NEW.agreed_unit_price, NEW.total_value, NEW.created_at,
        NEW.requirements)
       IS DISTINCT FROM
       (OLD.order_number, OLD.negotiation_id, OLD.negotiation_version_id, OLD.buyer_user_id, OLD.supplier_user_id,
        OLD.product_id, OLD.quantity, OLD.uom, OLD.currency, OLD.agreed_unit_price, OLD.total_value, OLD.created_at,
        OLD.requirements) THEN
        RAISE EXCEPTION 'order % terms are immutable', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        (OLD.status = 'placed' AND NEW.status IN ('confirmed', 'cancelled')) OR
        (OLD.status = 'confirmed' AND NEW.status IN ('processing', 'cancelled')) OR
        (OLD.status = 'processing' AND NEW.status = 'ready') OR
        (OLD.status = 'ready' AND NEW.status = 'dispatched') OR
        (OLD.status = 'dispatched' AND NEW.status = 'delivered')
    ) THEN
        RAISE EXCEPTION 'order % cannot move from % to %', OLD.id, OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
"""


def _status_checks(values: str) -> None:
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_status")
    op.execute(f"ALTER TABLE orders ADD CONSTRAINT ck_orders_status CHECK (status IN ({values}))")
    op.execute("ALTER TABLE order_status_events DROP CONSTRAINT IF EXISTS ck_order_status_events_from_status")
    op.execute(
        "ALTER TABLE order_status_events ADD CONSTRAINT ck_order_status_events_from_status "
        f"CHECK (from_status IS NULL OR from_status IN ({values}))"
    )
    op.execute("ALTER TABLE order_status_events DROP CONSTRAINT IF EXISTS ck_order_status_events_to_status")
    op.execute(
        "ALTER TABLE order_status_events ADD CONSTRAINT ck_order_status_events_to_status "
        f"CHECK (to_status IN ({values}))"
    )


def upgrade() -> None:
    op.add_column("orders", sa.Column("shipment_lr", sa.String(length=40), nullable=True))
    op.add_column("orders", sa.Column("shipment_transporter", sa.String(length=80), nullable=True))
    op.add_column("orders", sa.Column("shipment_vehicle", sa.String(length=40), nullable=True))
    op.add_column("orders", sa.Column("shipment_eta", sa.Date(), nullable=True))
    _status_checks(STATUSES)
    op.execute(ORDERS_GUARD)


def downgrade() -> None:
    op.execute(PREVIOUS_GUARD)
    _status_checks(PREVIOUS_STATUSES)
    op.drop_column("orders", "shipment_eta")
    op.drop_column("orders", "shipment_vehicle")
    op.drop_column("orders", "shipment_transporter")
    op.drop_column("orders", "shipment_lr")
