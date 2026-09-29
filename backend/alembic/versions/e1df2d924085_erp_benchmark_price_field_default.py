"""erp benchmark price field default

Revision ID: e1df2d924085
Revises: 410fac54e2de
Create Date: 2026-09-29 11:12:21.328041

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1df2d924085'
down_revision: Union[str, Sequence[str], None] = '410fac54e2de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE rate_sources
        SET normalization_profile = normalization_profile || jsonb_build_object(
                'benchmark_field', 'GrandTotal',
                'value_field', 'GrandTotal',
                'must_equal_fields', '[]'::jsonb
            ),
            profile_version = profile_version + 1
        WHERE code = 'ERP-DOMESTICPRICE1'
          AND COALESCE(normalization_profile->>'benchmark_field', '') = ''
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE rate_sources
        SET normalization_profile = (normalization_profile - 'benchmark_field') || jsonb_build_object(
                'value_field', 'UnitPrice',
                'must_equal_fields', '["Basic", "Total", "GrandTotal"]'::jsonb
            )
        WHERE code = 'ERP-DOMESTICPRICE1'
          AND normalization_profile->>'benchmark_field' = 'GrandTotal'
        """
    )
