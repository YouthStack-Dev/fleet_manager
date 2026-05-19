"""Add actual_start_time and actual_end_time to route_management.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-05-17 10:00:00.000000

Changes:
1. Add `actual_start_time` (DateTime, nullable) to `route_management`
2. Add `actual_end_time`   (DateTime, nullable) to `route_management`
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision      = "h2i3j4k5l6m7"
down_revision = "g1h2i3j4k5l6"
branch_labels = None
depends_on    = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade():
    bind = op.get_bind()

    if not _has_column(bind, "route_management", "actual_start_time"):
        op.add_column(
            "route_management",
            sa.Column("actual_start_time", sa.DateTime(), nullable=True),
        )

    if not _has_column(bind, "route_management", "actual_end_time"):
        op.add_column(
            "route_management",
            sa.Column("actual_end_time", sa.DateTime(), nullable=True),
        )


def downgrade():
    bind = op.get_bind()

    if _has_column(bind, "route_management", "actual_end_time"):
        op.drop_column("route_management", "actual_end_time")

    if _has_column(bind, "route_management", "actual_start_time"):
        op.drop_column("route_management", "actual_start_time")
