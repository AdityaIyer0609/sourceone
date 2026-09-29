"""Set the default road-distance freight rate at ₹2 per km.

Revision ID: f1a6b3c84d10
Revises: e4c8a91b6d02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f1a6b3c84d10"
down_revision: Union[str, Sequence[str], None] = "e4c8a91b6d02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO freight_distance_rates (id, currency, rate_per_km, minimum_freight, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), 'INR', 2.0000, NULL, true, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM freight_distance_rates WHERE currency = 'INR')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM freight_distance_rates
        WHERE currency = 'INR' AND rate_per_km = 2.0000 AND minimum_freight IS NULL
        """
    )
