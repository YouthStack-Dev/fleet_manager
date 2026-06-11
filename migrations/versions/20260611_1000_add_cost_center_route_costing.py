"""add cost center and route costing tables

Revision ID: 20260611_costing
Revises: 20260527_stale
Create Date: 2026-06-11 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_costing"
down_revision = "20260527_stale"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
