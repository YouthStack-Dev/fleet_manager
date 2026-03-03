"""add_escort_password

Revision ID: 20260303_add_escort_password
Revises: 20260303_rm_booking_escort_otp
Create Date: 2026-03-03

Purpose:
Adds a `password` column (SHA-256 hex, VARCHAR 64) to the `escorts` table so
escorts can authenticate via the escort mobile-app login endpoint.

The column is nullable so existing escort records are unaffected. Admins can
set/reset passwords through the management console. The value stored is always
a SHA-256 hex digest (no plain text stored).
"""
from alembic import op
import sqlalchemy as sa

revision = '20260303_add_escort_password'
down_revision = '20260303_rm_booking_escort_otp'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'escorts',
        sa.Column('password', sa.String(64), nullable=True)
    )


def downgrade():
    op.drop_column('escorts', 'password')
