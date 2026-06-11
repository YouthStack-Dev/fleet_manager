"""add vehicle rate distance slabs

Revision ID: 20260611_rate_slabs
Revises: 20260611_costing
Create Date: 2026-06-11 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_rate_slabs"
down_revision = "20260611_costing"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
