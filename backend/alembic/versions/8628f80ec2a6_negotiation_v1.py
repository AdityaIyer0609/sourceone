"""negotiation v1: negotiations, immutable offer versions, snapshot guard and permissions

Revision ID: 8628f80ec2a6
Revises: c1be8c1da225
Create Date: 2026-09-28 16:27:42.037003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8628f80ec2a6'
down_revision: Union[str, Sequence[str], None] = 'c1be8c1da225'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VERSIONS_GUARD = """
CREATE FUNCTION negotiation_versions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'negotiation versions are immutable (% rejected)', TG_OP
        USING ERRCODE = 'check_violation';
END $$;
CREATE TRIGGER negotiation_versions_guard BEFORE UPDATE OR DELETE ON negotiation_versions
    FOR EACH ROW EXECUTE FUNCTION negotiation_versions_guard();
"""

NEGOTIATIONS_GUARD = """
CREATE FUNCTION negotiations_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
CREATE TRIGGER negotiations_guard BEFORE UPDATE OR DELETE ON negotiations
    FOR EACH ROW EXECUTE FUNCTION negotiations_guard();
"""

VERSION_ON_ACTIVE = """
CREATE FUNCTION negotiation_versions_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent negotiations%ROWTYPE;
BEGIN
    SELECT * INTO parent FROM negotiations WHERE id = NEW.negotiation_id;
    IF parent.status IN ('accepted', 'rejected', 'cancelled') THEN
        RAISE EXCEPTION 'negotiation % is % and cannot receive offers', parent.id, parent.status
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.currency <> parent.currency OR NEW.uom <> parent.uom THEN
        RAISE EXCEPTION 'offer must be in % per %', parent.currency, parent.uom USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER negotiation_versions_insert_guard BEFORE INSERT ON negotiation_versions
    FOR EACH ROW EXECUTE FUNCTION negotiation_versions_insert_guard();
"""

PERMISSIONS = [
    ("negotiation.buy", "Start negotiations and respond as the buyer"),
    ("negotiation.supply", "Respond to assigned negotiations as the supplier"),
]
ROLE_PERMISSIONS = {"buyer": "negotiation.buy", "supplier": "negotiation.supply"}


def upgrade() -> None:
    op.create_table('negotiations',
    sa.Column('negotiation_number', sa.String(length=32), nullable=False),
    sa.Column('buyer_user_id', sa.Uuid(), nullable=False),
    sa.Column('supplier_user_id', sa.Uuid(), nullable=False),
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('rate_series_id', sa.Uuid(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('uom', sa.String(length=16), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('benchmark_state', sa.String(length=16), nullable=False),
    sa.Column('benchmark_rate_id', sa.Uuid(), nullable=True),
    sa.Column('benchmark_rate_snapshot', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('benchmark_as_of', sa.Date(), nullable=True),
    sa.Column('benchmark_series_code', sa.String(length=160), nullable=True),
    sa.Column('benchmark_basis', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('accepted_version_id', sa.Uuid(), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('closed_reason', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(benchmark_state = 'rate_on_request') = (benchmark_rate_snapshot IS NULL)", name=op.f('ck_negotiations_snapshot_matches_state')),
    sa.CheckConstraint("(status = 'accepted') = (accepted_version_id IS NOT NULL)", name=op.f('ck_negotiations_accepted_has_version')),
    sa.CheckConstraint("(status IN ('accepted', 'rejected', 'cancelled')) = (closed_at IS NOT NULL)", name=op.f('ck_negotiations_closed_iff_terminal')),
    sa.CheckConstraint("benchmark_state IN ('fresh', 'stale', 'rate_on_request')", name=op.f('ck_negotiations_benchmark_state')),
    sa.CheckConstraint("currency IN ('INR', 'USD')", name=op.f('ck_negotiations_currency')),
    sa.CheckConstraint("status IN ('draft', 'open', 'countered', 'accepted', 'rejected', 'cancelled')", name=op.f('ck_negotiations_status')),
    sa.CheckConstraint("uom IN ('KG')", name=op.f('ck_negotiations_uom')),
    sa.CheckConstraint('buyer_user_id <> supplier_user_id', name=op.f('ck_negotiations_distinct_parties')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_negotiations_quantity_positive')),
    sa.ForeignKeyConstraint(['benchmark_rate_id'], ['benchmark_rates.id'], name=op.f('fk_negotiations_benchmark_rate_id_benchmark_rates')),
    sa.ForeignKeyConstraint(['buyer_user_id'], ['users.id'], name=op.f('fk_negotiations_buyer_user_id_users')),
    sa.ForeignKeyConstraint(['closed_by_user_id'], ['users.id'], name=op.f('fk_negotiations_closed_by_user_id_users')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_negotiations_product_id_products')),
    sa.ForeignKeyConstraint(['rate_series_id'], ['rate_series.id'], name=op.f('fk_negotiations_rate_series_id_rate_series')),
    sa.ForeignKeyConstraint(['supplier_user_id'], ['users.id'], name=op.f('fk_negotiations_supplier_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_negotiations')),
    sa.UniqueConstraint('negotiation_number', name=op.f('uq_negotiations_negotiation_number'))
    )
    op.create_index('ix_negotiations_buyer_status', 'negotiations', ['buyer_user_id', 'status'], unique=False)
    op.create_index(op.f('ix_negotiations_product_id'), 'negotiations', ['product_id'], unique=False)
    op.create_index('ix_negotiations_supplier_status', 'negotiations', ['supplier_user_id', 'status'], unique=False)
    op.create_table('negotiation_versions',
    sa.Column('negotiation_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('created_by_user_id', sa.Uuid(), nullable=False),
    sa.Column('offered_price', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=18, scale=3), nullable=False),
    sa.Column('uom', sa.String(length=16), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("currency IN ('INR', 'USD')", name=op.f('ck_negotiation_versions_currency')),
    sa.CheckConstraint("uom IN ('KG')", name=op.f('ck_negotiation_versions_uom')),
    sa.CheckConstraint('offered_price > 0', name=op.f('ck_negotiation_versions_offered_price_positive')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_negotiation_versions_quantity_positive')),
    sa.CheckConstraint('version_number > 0', name=op.f('ck_negotiation_versions_version_number_positive')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_negotiation_versions_created_by_user_id_users')),
    sa.ForeignKeyConstraint(['negotiation_id'], ['negotiations.id'], name=op.f('fk_negotiation_versions_negotiation_id_negotiations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_negotiation_versions')),
    sa.UniqueConstraint('negotiation_id', 'version_number', name='uq_negotiation_versions_number')
    )
    op.create_foreign_key(
        op.f('fk_negotiations_accepted_version_id_negotiation_versions'),
        'negotiations', 'negotiation_versions', ['accepted_version_id'], ['id'],
    )

    op.execute("CREATE SEQUENCE negotiation_number_seq OWNED BY negotiations.negotiation_number")
    op.execute(VERSIONS_GUARD)
    op.execute(VERSION_ON_ACTIVE)
    op.execute(NEGOTIATIONS_GUARD)

    for code, description in PERMISSIONS:
        op.execute(
            f"INSERT INTO permissions (id, code, description) VALUES (gen_random_uuid(), '{code}', '{description}')"
        )
    for role, permission in ROLE_PERMISSIONS.items():
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            f"SELECT r.id, p.id FROM roles r, permissions p WHERE r.code = '{role}' AND p.code = '{permission}'"
        )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for code, _ in PERMISSIONS)
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes})")
    op.execute("DROP TRIGGER negotiations_guard ON negotiations")
    op.execute("DROP FUNCTION negotiations_guard()")
    op.execute("DROP TRIGGER negotiation_versions_insert_guard ON negotiation_versions")
    op.execute("DROP FUNCTION negotiation_versions_insert_guard()")
    op.execute("DROP TRIGGER negotiation_versions_guard ON negotiation_versions")
    op.execute("DROP FUNCTION negotiation_versions_guard()")
    op.drop_constraint(
        op.f('fk_negotiations_accepted_version_id_negotiation_versions'), 'negotiations', type_='foreignkey'
    )
    op.drop_table('negotiation_versions')
    op.drop_index('ix_negotiations_supplier_status', table_name='negotiations')
    op.drop_index(op.f('ix_negotiations_product_id'), table_name='negotiations')
    op.drop_index('ix_negotiations_buyer_status', table_name='negotiations')
    op.drop_table('negotiations')
