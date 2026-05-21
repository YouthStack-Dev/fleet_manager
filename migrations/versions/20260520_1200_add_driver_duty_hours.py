"""add driver duty hours enforcement to tenant_configs

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-05-20 12:00:00

Feature 1 — Driver Duty Hours & Rest-Time Enforcement
Adds two columns to tenant_configs:
  - driver_max_duty_minutes  INT  DEFAULT 600  (e.g. 10 hours)
  - driver_rest_enforcement  VARCHAR(10) DEFAULT 'warn'  ('warn' | 'block')
"""
from alembic import op
import sqlalchemy as sa

# Alembic revision identifiers
revision      = "n8o9p0q1r2s3"
down_revision = "m7n8o9p0q1r2"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "tenant_configs",
        sa.Column("driver_max_duty_minutes", sa.Integer(), nullable=False, server_default="600"),
    )
    op.add_column(
        "tenant_configs",
        sa.Column("driver_rest_enforcement", sa.String(10), nullable=False, server_default="warn"),
    )


def downgrade() -> None:
    op.drop_column("tenant_configs", "driver_rest_enforcement")
    op.drop_column("tenant_configs", "driver_max_duty_minutes")
