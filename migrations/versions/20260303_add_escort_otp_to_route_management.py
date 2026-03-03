"""add_escort_otp_and_escort_boarded_to_route_management

Revision ID: 20260303_escort_otp
Revises: 20260302_notif_logs
Create Date: 2026-03-03

Purpose:
Move escort OTP to route level so the escort holds a single OTP that
the driver verifies verbally before picking up employees.

- escort_otp:     Single 4-digit OTP generated per dispatch; sent to the escort via SMS.
- escort_boarded: Flag set to True once the driver has verified the escort OTP via the
                  POST /driver/escort/board endpoint.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260303_escort_otp'
down_revision = '20260302_notif_logs'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'route_management',
        sa.Column('escort_otp', sa.Integer(), nullable=True)
    )
    op.add_column(
        'route_management',
        sa.Column('escort_boarded', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade():
    op.drop_column('route_management', 'escort_boarded')
    op.drop_column('route_management', 'escort_otp')
