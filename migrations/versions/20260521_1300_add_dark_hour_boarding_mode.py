"""add dark_hour_boarding_mode to tenant_configs

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-05-21 13:00:00

Feature 12 — Female Employee Dark-Hour Boarding Block
Adds one column to tenant_configs:
  - dark_hour_boarding_mode  VARCHAR(10) DEFAULT 'off'
    ('off' | 'warn' | 'block')
"""
from alembic import op
import sqlalchemy as sa

# Alembic revision identifiers
revision      = "o9p0q1r2s3t4"
down_revision = "n8o9p0q1r2s3"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "tenant_configs",
        sa.Column(
            "dark_hour_boarding_mode",
            sa.String(10),
            nullable=False,
            server_default="off",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_configs", "dark_hour_boarding_mode")
