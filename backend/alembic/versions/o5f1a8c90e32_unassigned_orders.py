"""An order can be placed before a supplier is assigned.

Revision ID: o5f1a8c90e32
Revises: n4e0f7b89d21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "o5f1a8c90e32"
down_revision: Union[str, Sequence[str], None] = "n4e0f7b89d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INSERT_GUARD = """
CREATE OR REPLACE FUNCTION orders_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    n negotiations%ROWTYPE;
    v negotiation_versions%ROWTYPE;
BEGIN
    IF NEW.negotiation_id IS NULL THEN
        IF NEW.supplier_user_id IS NOT NULL OR NEW.negotiation_version_id IS NOT NULL THEN
            RAISE EXCEPTION 'an unassigned order has no supplier' USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.status <> 'placed' THEN
            RAISE EXCEPTION 'new orders start as placed' USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    SELECT * INTO n FROM negotiations WHERE id = NEW.negotiation_id;
    IF n.status <> 'accepted' OR n.accepted_version_id IS DISTINCT FROM NEW.negotiation_version_id THEN
        RAISE EXCEPTION 'orders can only be placed from the accepted version of an accepted negotiation'
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO v FROM negotiation_versions WHERE id = NEW.negotiation_version_id;
    IF (NEW.buyer_user_id, NEW.supplier_user_id, NEW.product_id, NEW.quantity, NEW.uom, NEW.currency,
        NEW.agreed_unit_price)
       IS DISTINCT FROM (n.buyer_user_id, n.supplier_user_id, n.product_id, v.quantity, v.uom, v.currency,
        v.offered_price) THEN
        RAISE EXCEPTION 'order terms must equal the accepted negotiation version' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status <> 'placed' THEN
        RAISE EXCEPTION 'new orders start as placed' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
"""

UPDATE_GUARD = """
CREATE OR REPLACE FUNCTION orders_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'order % cannot be deleted', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status IN ('delivered', 'cancelled') THEN
        RAISE EXCEPTION 'order % is % and is final', OLD.id, OLD.status USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.negotiation_id IS NULL AND OLD.supplier_user_id IS NULL THEN
        IF (NEW.order_number, NEW.buyer_user_id, NEW.product_id, NEW.quantity, NEW.uom, NEW.currency,
            NEW.agreed_unit_price, NEW.total_value, NEW.created_at, NEW.requirements)
           IS DISTINCT FROM
           (OLD.order_number, OLD.buyer_user_id, OLD.product_id, OLD.quantity, OLD.uom, OLD.currency,
            OLD.agreed_unit_price, OLD.total_value, OLD.created_at, OLD.requirements) THEN
            RAISE EXCEPTION 'order % terms are immutable', OLD.id USING ERRCODE = 'check_violation';
        END IF;
        IF (NEW.supplier_user_id IS NOT NULL OR NEW.negotiation_id IS NOT NULL OR NEW.negotiation_version_id IS NOT NULL)
           AND (NEW.supplier_user_id IS NULL OR NEW.negotiation_id IS NULL OR NEW.negotiation_version_id IS NULL) THEN
            RAISE EXCEPTION 'assignment needs a supplier and an accepted negotiation' USING ERRCODE = 'check_violation';
        END IF;
    ELSIF (NEW.order_number, NEW.negotiation_id, NEW.negotiation_version_id, NEW.buyer_user_id, NEW.supplier_user_id,
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


def upgrade() -> None:
    op.alter_column("orders", "negotiation_id", nullable=True)
    op.alter_column("orders", "negotiation_version_id", nullable=True)
    op.alter_column("orders", "supplier_user_id", nullable=True)
    op.execute(INSERT_GUARD)
    op.execute(UPDATE_GUARD)


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_supplier_present")
    op.alter_column("orders", "supplier_user_id", nullable=False)
    op.alter_column("orders", "negotiation_version_id", nullable=False)
    op.alter_column("orders", "negotiation_id", nullable=False)
