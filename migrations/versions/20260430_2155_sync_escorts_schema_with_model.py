"""sync escorts schema with model

Revision ID: e7f8a9b0c1d2
Revises: d1e2f3a4b5c6
Create Date: 2026-04-30 21:55:00.000000

Ensures the escorts table contains all columns used by current Escort model
and escort endpoints.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e7f8a9b0c1d2"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "escorts"):
        return

    if not _has_column(bind, "escorts", "email"):
        op.add_column("escorts", sa.Column("email", sa.String(length=100), nullable=True))

    if not _has_column(bind, "escorts", "address"):
        op.add_column("escorts", sa.Column("address", sa.Text(), nullable=True))

    if not _has_column(bind, "escorts", "is_available"):
        op.add_column(
            "escorts",
            sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        op.alter_column("escorts", "is_available", server_default=None)

    if not _has_column(bind, "escorts", "gender"):
        op.add_column("escorts", sa.Column("gender", sa.String(length=10), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "escorts"):
        return

    for col in ["gender", "is_available", "address", "email"]:
        if _has_column(bind, "escorts", col):
            op.drop_column("escorts", col)
