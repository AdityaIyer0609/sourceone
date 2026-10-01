"""Supplier product submissions for pricing-admin review.

Revision ID: h8e4f1b23d55
Revises: g7d3e9a12c44
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h8e4f1b23d55"
down_revision: Union[str, Sequence[str], None] = "g7d3e9a12c44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_submissions",
        sa.Column("supplier_user_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("subcategory", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uom", sa.String(length=16), nullable=False),
        sa.Column("specifications", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("asking_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("minimum_quantity", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("availability", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'rejected')", name=op.f("ck_product_submissions_status")),
        sa.CheckConstraint(
            "(status = 'pending') = (reviewed_at IS NULL AND reviewed_by_user_id IS NULL AND product_id IS NULL)",
            name=op.f("ck_product_submissions_pending_unreviewed"),
        ),
        sa.CheckConstraint("(status = 'accepted') = (product_id IS NOT NULL)", name=op.f("ck_product_submissions_accepted_has_product")),
        sa.CheckConstraint("uom = 'KG'", name=op.f("ck_product_submissions_uom")),
        sa.CheckConstraint("asking_price > 0", name=op.f("ck_product_submissions_asking_price_positive")),
        sa.CheckConstraint("minimum_quantity > 0", name=op.f("ck_product_submissions_minimum_quantity_positive")),
        sa.CheckConstraint("currency IN ('INR', 'USD')", name=op.f("ck_product_submissions_currency")),
        sa.CheckConstraint("availability IN ('in_stock', 'limited', 'on_request')", name=op.f("ck_product_submissions_availability")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_product_submissions_product_id_products")),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], name=op.f("fk_product_submissions_reviewed_by_user_id_users")),
        sa.ForeignKeyConstraint(["supplier_user_id"], ["users.id"], name=op.f("fk_product_submissions_supplier_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_submissions")),
    )
    op.create_index(op.f("ix_product_submissions_supplier_user_id"), "product_submissions", ["supplier_user_id"], unique=False)
    op.create_index(
        "uq_product_submissions_pending_code",
        "product_submissions",
        ["supplier_user_id", "proposed_code"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_product_submissions_pending_code", table_name="product_submissions")
    op.drop_index(op.f("ix_product_submissions_supplier_user_id"), table_name="product_submissions")
    op.drop_table("product_submissions")
