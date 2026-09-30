"""Company approval threshold and order approval requests.

Revision ID: e5b8a1c04d26
Revises: d2b7c4e81a05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b8a1c04d26"
down_revision: Union[str, Sequence[str], None] = "d2b7c4e81a05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEGOTIATIONS_GUARD = """
CREATE OR REPLACE FUNCTION negotiations_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'negotiation % cannot be deleted', OLD.id USING ERRCODE = 'check_violation';
    END IF;

    IF OLD.status IN ('rejected', 'cancelled') THEN
        RAISE EXCEPTION 'negotiation % is % and is final', OLD.id, OLD.status USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status = 'accepted' AND NEW.status IS DISTINCT FROM OLD.status AND NEW.status <> 'cancelled' THEN
        RAISE EXCEPTION 'negotiation % is accepted and is final', OLD.id USING ERRCODE = 'check_violation';
    END IF;

    IF (NEW.negotiation_number, NEW.buyer_user_id, NEW.supplier_user_id, NEW.product_id, NEW.rate_series_id,
        NEW.uom, NEW.currency, NEW.benchmark_state, NEW.benchmark_rate_id, NEW.benchmark_rate_snapshot,
        NEW.benchmark_as_of, NEW.benchmark_series_code, NEW.benchmark_basis, NEW.created_at)
       IS DISTINCT FROM
       (OLD.negotiation_number, OLD.buyer_user_id, OLD.supplier_user_id, OLD.product_id, OLD.rate_series_id,
        OLD.uom, OLD.currency, OLD.benchmark_state, OLD.benchmark_rate_id, OLD.benchmark_rate_snapshot,
        OLD.benchmark_as_of, OLD.benchmark_series_code, OLD.benchmark_basis, OLD.created_at) THEN
        RAISE EXCEPTION 'negotiation % parties, terms and benchmark snapshot are immutable', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        (OLD.status = 'draft' AND NEW.status IN ('open', 'cancelled')) OR
        (OLD.status IN ('open', 'countered') AND NEW.status IN ('countered', 'accepted', 'rejected', 'cancelled')) OR
        (OLD.status = 'accepted' AND NEW.status = 'cancelled')
    ) THEN
        RAISE EXCEPTION 'negotiation % cannot move from % to %', OLD.id, OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.accepted_version_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM negotiation_versions v WHERE v.id = NEW.accepted_version_id AND v.negotiation_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'accepted version does not belong to negotiation %', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
"""


def upgrade() -> None:
    op.add_column("organisations", sa.Column("approval_threshold_amount", sa.Numeric(20, 2), nullable=True))
    op.add_column("organisations", sa.Column("approval_threshold_currency", sa.String(length=3), nullable=True))
    op.create_check_constraint(
        "ck_organisations_approval_threshold",
        "organisations",
        "(approval_threshold_amount IS NULL AND approval_threshold_currency IS NULL) "
        "OR (approval_threshold_amount > 0 AND approval_threshold_currency IN ('INR', 'USD'))",
    )
    op.create_table(
        "order_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("negotiation_id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("threshold_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("threshold_currency", sa.String(length=3), nullable=False),
        sa.Column("destination_pin", sa.String(length=6), nullable=False),
        sa.Column("freight_basis", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decision_note", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'declined', 'deal_rejected')", name="ck_order_approvals_status"),
        sa.CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL AND decided_by_user_id IS NULL)",
            name="ck_order_approvals_decision",
        ),
        sa.CheckConstraint(
            "decided_by_user_id IS NULL OR decided_by_user_id <> submitted_by_user_id",
            name="ck_order_approvals_four_eyes",
        ),
        sa.CheckConstraint("amount > 0 AND threshold_amount > 0", name="ck_order_approvals_amounts"),
        sa.CheckConstraint("currency IN ('INR', 'USD') AND threshold_currency = currency", name="ck_order_approvals_currency"),
        sa.CheckConstraint("destination_pin ~ '^[1-9][0-9]{5}$'", name="ck_order_approvals_pin"),
        sa.CheckConstraint("freight_basis IN ('standard', 'distance')", name="ck_order_approvals_freight_basis"),
        sa.ForeignKeyConstraint(["negotiation_id"], ["negotiations.id"], name="fk_order_approvals_negotiation_id"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], name="fk_order_approvals_organisation_id"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], name="fk_order_approvals_submitted_by_user_id"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], name="fk_order_approvals_decided_by_user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_order_approvals"),
    )
    op.create_index(
        "uq_order_approvals_one_pending",
        "order_approvals",
        ["negotiation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_order_approvals_organisation", "order_approvals", ["organisation_id", "status"])
    op.execute(NEGOTIATIONS_GUARD)
    op.execute(
        "INSERT INTO permissions (id, code, description) VALUES "
        "(gen_random_uuid(), 'order.approve', 'Approve or decline an order above the company threshold'), "
        "(gen_random_uuid(), 'organisation.manage', 'Set the company order-approval threshold and see company users')"
    )
    op.execute(
        "INSERT INTO roles (id, code, name) VALUES (gen_random_uuid(), 'approver', 'Approver')"
    )
    for permission in ("order.approve", "organisation.manage", "pricing.view"):
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            f"SELECT r.id, p.id FROM roles r, permissions p WHERE r.code = 'approver' AND p.code = '{permission}'"
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE code = 'approver') "
        "OR permission_id IN (SELECT id FROM permissions WHERE code IN ('order.approve', 'organisation.manage'))"
    )
    op.execute("DELETE FROM roles WHERE code = 'approver'")
    op.execute("DELETE FROM permissions WHERE code IN ('order.approve', 'organisation.manage')")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION negotiations_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'negotiation % cannot be deleted', OLD.id USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.status IN ('accepted', 'rejected', 'cancelled') THEN
                RAISE EXCEPTION 'negotiation % is % and is final', OLD.id, OLD.status USING ERRCODE = 'check_violation';
            END IF;
            IF (NEW.negotiation_number, NEW.buyer_user_id, NEW.supplier_user_id, NEW.product_id, NEW.rate_series_id,
                NEW.uom, NEW.currency, NEW.benchmark_state, NEW.benchmark_rate_id, NEW.benchmark_rate_snapshot,
                NEW.benchmark_as_of, NEW.benchmark_series_code, NEW.benchmark_basis, NEW.created_at)
               IS DISTINCT FROM
               (OLD.negotiation_number, OLD.buyer_user_id, OLD.supplier_user_id, OLD.product_id, OLD.rate_series_id,
                OLD.uom, OLD.currency, OLD.benchmark_state, OLD.benchmark_rate_id, OLD.benchmark_rate_snapshot,
                OLD.benchmark_as_of, OLD.benchmark_series_code, OLD.benchmark_basis, OLD.created_at) THEN
                RAISE EXCEPTION 'negotiation % parties, terms and benchmark snapshot are immutable', OLD.id
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
                (OLD.status = 'draft' AND NEW.status IN ('open', 'cancelled')) OR
                (OLD.status IN ('open', 'countered') AND NEW.status IN ('countered', 'accepted', 'rejected', 'cancelled'))
            ) THEN
                RAISE EXCEPTION 'negotiation % cannot move from % to %', OLD.id, OLD.status, NEW.status
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.accepted_version_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM negotiation_versions v WHERE v.id = NEW.accepted_version_id AND v.negotiation_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'accepted version does not belong to negotiation %', NEW.id
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    op.drop_index("ix_order_approvals_organisation", table_name="order_approvals")
    op.drop_index("uq_order_approvals_one_pending", table_name="order_approvals")
    op.drop_table("order_approvals")
    op.drop_constraint("ck_organisations_approval_threshold", "organisations", type_="check")
    op.drop_column("organisations", "approval_threshold_currency")
    op.drop_column("organisations", "approval_threshold_amount")
