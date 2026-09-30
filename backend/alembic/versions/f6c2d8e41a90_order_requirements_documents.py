"""Freeze requirement snapshots and store order fulfilment documents.

Revision ID: f6c2d8e41a90
Revises: e5b8a1c04d26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6c2d8e41a90"
down_revision: Union[str, Sequence[str], None] = "e5b8a1c04d26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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
        (OLD.status = 'dispatched' AND NEW.status = 'delivered')
    ) THEN
        RAISE EXCEPTION 'order % cannot move from % to %', OLD.id, OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
"""


def upgrade() -> None:
    op.add_column("negotiations", sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("orders", sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        "requirement_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("negotiation_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_key", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('met', 'not_met')", name="ck_requirement_responses_status"),
        sa.ForeignKeyConstraint(["negotiation_id"], ["negotiations.id"], name="fk_requirement_responses_negotiation_id"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], name="fk_requirement_responses_updated_by_user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_requirement_responses"),
        sa.UniqueConstraint("negotiation_id", "requirement_key", name="uq_requirement_responses_key"),
    )
    op.create_table(
        "order_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("stored_name", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "document_type IN ('coa', 'mtc', 'test_certificate', 'inspection_report', 'invoice', 'lr', 'eway_bill', 'packing_list', 'pod')",
            name="ck_order_documents_type",
        ),
        sa.CheckConstraint("status IN ('submitted', 'accepted', 'rejected')", name="ck_order_documents_status"),
        sa.CheckConstraint("byte_size > 0", name="ck_order_documents_size"),
        sa.CheckConstraint(
            "(status = 'submitted') = (reviewed_at IS NULL AND reviewed_by_user_id IS NULL)",
            name="ck_order_documents_review",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_documents_order_id"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], name="fk_order_documents_uploaded_by_user_id"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], name="fk_order_documents_reviewed_by_user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_order_documents"),
        sa.UniqueConstraint("stored_name", name="uq_order_documents_stored_name"),
    )
    op.create_index("ix_order_documents_order", "order_documents", ["order_id"])
    op.execute(ORDERS_GUARD)


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION orders_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'order % cannot be deleted', OLD.id USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.status IN ('delivered', 'cancelled') THEN
                RAISE EXCEPTION 'order % is % and is final', OLD.id, OLD.status USING ERRCODE = 'check_violation';
            END IF;
            IF (NEW.order_number, NEW.negotiation_id, NEW.negotiation_version_id, NEW.buyer_user_id, NEW.supplier_user_id,
                NEW.product_id, NEW.quantity, NEW.uom, NEW.currency, NEW.agreed_unit_price, NEW.total_value, NEW.created_at)
               IS DISTINCT FROM
               (OLD.order_number, OLD.negotiation_id, OLD.negotiation_version_id, OLD.buyer_user_id, OLD.supplier_user_id,
                OLD.product_id, OLD.quantity, OLD.uom, OLD.currency, OLD.agreed_unit_price, OLD.total_value, OLD.created_at) THEN
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
    )
    op.drop_index("ix_order_documents_order", table_name="order_documents")
    op.drop_table("order_documents")
    op.drop_table("requirement_responses")
    op.drop_column("orders", "requirements")
    op.drop_column("negotiations", "requirements")
