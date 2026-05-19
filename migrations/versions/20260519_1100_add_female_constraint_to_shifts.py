"""Add female_constraint column to shifts table.

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-05-19 11:00:00.000000

Changes:
1. Add `female_constraint` (VARCHAR, nullable) to `shifts`
   Valid values: 'First/Last Female', 'Second/Second Last Female', 'Any Female', 'Disable'
   NULL means: no shift-level override — fall back to tenant escort config.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision      = "i3j4k5l6m7n8"
down_revision = "h2i3j4k5l6m7"
branch_labels = None
depends_on    = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade():
    bind = op.get_bind()

    if not _has_column(bind, "shifts", "female_constraint"):
        op.add_column(
            "shifts",
            sa.Column(
                "female_constraint",
                sa.String(50),
                nullable=True,
                comment=(
                    "Escort rule for female passengers on this shift. "
                    "NULL = use tenant escort config. "
                    "Values: First/Last Female | Second/Second Last Female | Any Female | Disable"
                ),
            ),
        )


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "shifts", "female_constraint"):
        op.drop_column("shifts", "female_constraint")
