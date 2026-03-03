"""remove_escort_otp_from_bookings

Revision ID: 20260303_rm_booking_escort_otp
Revises: 20260303_escort_otp
Create Date: 2026-03-03

Purpose:
Escort OTP is now a single route-level field on route_management.escort_otp.
The per-booking escort_otp column is no longer needed and is removed here.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260303_rm_booking_escort_otp'
down_revision = '20260303_escort_otp'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('bookings', 'escort_otp')


def downgrade():
    op.add_column(
        'bookings',
        sa.Column('escort_otp', sa.Integer(), nullable=True)
    )
