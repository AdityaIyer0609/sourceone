"""pricing integrity triggers and role/permission reference data

Revision ID: a7c3e9d21f04
Revises: cefda1eeff3e
Create Date: 2026-09-28 15:40:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a7c3e9d21f04"
down_revision: Union[str, Sequence[str], None] = "cefda1eeff3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BENCHMARK_GUARD = """
CREATE FUNCTION benchmark_rates_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status IN ('published', 'withdrawn', 'rejected') THEN
            RAISE EXCEPTION 'benchmark % is % and cannot be deleted', OLD.id, OLD.status
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN OLD;
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        (OLD.status = 'draft' AND NEW.status IN ('submitted', 'rejected')) OR
        (OLD.status = 'submitted' AND NEW.status IN ('published', 'rejected')) OR
        (OLD.status = 'published' AND NEW.status = 'withdrawn')
    ) THEN
        RAISE EXCEPTION 'invalid benchmark transition % -> %', OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;

    IF OLD.status IN ('withdrawn', 'rejected') THEN
        RAISE EXCEPTION 'benchmark % is % and final', OLD.id, OLD.status
            USING ERRCODE = 'check_violation';
    END IF;

    IF OLD.status = 'published' THEN
        IF (NEW.series_id, NEW.primary_source_id, NEW.value, NEW.currency, NEW.unit,
            NEW.price_basis, NEW.tax_basis, NEW.method, NEW.origin, NEW.is_edited,
            NEW.four_eyes_required, NEW.source_as_of_date, NEW.effective_from,
            NEW.staleness_days, NEW.stale_after, NEW.reason, NEW.evidence_ref,
            NEW.created_by_id, NEW.created_at, NEW.last_edited_by_id, NEW.last_edited_at,
            NEW.submitted_by_id, NEW.submitted_at, NEW.published_by_id, NEW.published_at)
           IS DISTINCT FROM
           (OLD.series_id, OLD.primary_source_id, OLD.value, OLD.currency, OLD.unit,
            OLD.price_basis, OLD.tax_basis, OLD.method, OLD.origin, OLD.is_edited,
            OLD.four_eyes_required, OLD.source_as_of_date, OLD.effective_from,
            OLD.staleness_days, OLD.stale_after, OLD.reason, OLD.evidence_ref,
            OLD.created_by_id, OLD.created_at, OLD.last_edited_by_id, OLD.last_edited_at,
            OLD.submitted_by_id, OLD.submitted_at, OLD.published_by_id, OLD.published_at)
        THEN
            RAISE EXCEPTION 'published benchmark % is immutable', OLD.id
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.effective_until IS DISTINCT FROM OLD.effective_until AND (
            NEW.effective_until IS NULL OR
            (OLD.effective_until IS NOT NULL AND NEW.effective_until > OLD.effective_until)
        ) THEN
            RAISE EXCEPTION 'effective_until of published benchmark % may only be shortened', OLD.id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""

INPUT_GUARD = """
CREATE FUNCTION benchmark_rate_inputs_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_status text;
BEGIN
    SELECT status INTO parent_status FROM benchmark_rates
     WHERE id = COALESCE(NEW.benchmark_rate_id, OLD.benchmark_rate_id);
    IF parent_status IN ('published', 'withdrawn', 'rejected') THEN
        RAISE EXCEPTION 'inputs of a % benchmark are immutable', parent_status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;
"""

APPEND_ONLY = """
CREATE FUNCTION pricing_audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'pricing_audit_events is append-only' USING ERRCODE = 'check_violation';
END;
$$;
"""

SOURCE_RATE_GUARD = """
CREATE FUNCTION source_rates_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.source_id, NEW.import_batch_id, NEW.source_row_ref, NEW.source_row_key,
        NEW.source_identity_key, NEW.source_as_of_date, NEW.value, NEW.currency, NEW.unit,
        NEW.raw_producer, NEW.raw_grade, NEW.raw_location, NEW.raw_sector, NEW.raw_payload)
       IS DISTINCT FROM
       (OLD.source_id, OLD.import_batch_id, OLD.source_row_ref, OLD.source_row_key,
        OLD.source_identity_key, OLD.source_as_of_date, OLD.value, OLD.currency, OLD.unit,
        OLD.raw_producer, OLD.raw_grade, OLD.raw_location, OLD.raw_sector, OLD.raw_payload)
    THEN
        RAISE EXCEPTION 'source rate % facts are immutable', OLD.id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

ROLES = [
    ("platform_admin", "Platform administrator"),
    ("pricing_admin", "Pricing administrator"),
    ("buyer", "Buyer"),
    ("supplier", "Supplier"),
]
PERMISSIONS = [
    ("pricing.view", "View published SourceOne benchmarks"),
    ("pricing.edit", "Create and edit benchmark candidates"),
    ("pricing.publish", "Publish, reject and withdraw benchmarks"),
    ("pricing.configure", "Configure rate sources, series and mappings"),
]
ROLE_PERMISSIONS = {
    "platform_admin": ["pricing.view", "pricing.edit", "pricing.publish", "pricing.configure"],
    "pricing_admin": ["pricing.view", "pricing.edit", "pricing.publish"],
    "buyer": ["pricing.view"],
    "supplier": ["pricing.view"],
}


def upgrade() -> None:
    op.execute(BENCHMARK_GUARD)
    op.execute(
        "CREATE TRIGGER trg_benchmark_rates_guard BEFORE UPDATE OR DELETE ON benchmark_rates "
        "FOR EACH ROW EXECUTE FUNCTION benchmark_rates_guard()"
    )
    op.execute(INPUT_GUARD)
    op.execute(
        "CREATE TRIGGER trg_benchmark_rate_inputs_guard BEFORE INSERT OR UPDATE OR DELETE "
        "ON benchmark_rate_inputs FOR EACH ROW EXECUTE FUNCTION benchmark_rate_inputs_guard()"
    )
    op.execute(APPEND_ONLY)
    op.execute(
        "CREATE TRIGGER trg_pricing_audit_events_append_only BEFORE UPDATE OR DELETE "
        "ON pricing_audit_events FOR EACH ROW EXECUTE FUNCTION pricing_audit_events_append_only()"
    )
    op.execute(SOURCE_RATE_GUARD)
    op.execute(
        "CREATE TRIGGER trg_source_rates_guard BEFORE UPDATE ON source_rates "
        "FOR EACH ROW EXECUTE FUNCTION source_rates_guard()"
    )

    for code, name in ROLES:
        op.execute(f"INSERT INTO roles (id, code, name) VALUES (gen_random_uuid(), '{code}', '{name}')")
    for code, description in PERMISSIONS:
        op.execute(
            f"INSERT INTO permissions (id, code, description) "
            f"VALUES (gen_random_uuid(), '{code}', '{description}')"
        )
    for role, permissions in ROLE_PERMISSIONS.items():
        codes = ", ".join(f"'{p}'" for p in permissions)
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            f"SELECT r.id, p.id FROM roles r, permissions p WHERE r.code = '{role}' AND p.code IN ({codes})"
        )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions")
    op.execute("DELETE FROM permissions")
    op.execute("DELETE FROM roles")
    op.execute("DROP TRIGGER IF EXISTS trg_source_rates_guard ON source_rates")
    op.execute("DROP FUNCTION IF EXISTS source_rates_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_pricing_audit_events_append_only ON pricing_audit_events")
    op.execute("DROP FUNCTION IF EXISTS pricing_audit_events_append_only()")
    op.execute("DROP TRIGGER IF EXISTS trg_benchmark_rate_inputs_guard ON benchmark_rate_inputs")
    op.execute("DROP FUNCTION IF EXISTS benchmark_rate_inputs_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_benchmark_rates_guard ON benchmark_rates")
    op.execute("DROP FUNCTION IF EXISTS benchmark_rates_guard()")
