"""add_notification_logs_table

Revision ID: 20260302_notif_logs
Revises: 00a6c88b8420
Create Date: 2026-03-02

Purpose:
Track every batch of Email/SMS/Push notifications dispatched for a route.
One row is inserted per dispatch (vehicle assignment or manual resend).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = '20260302_notif_logs'
down_revision = '00a6c88b8420'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notification_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('route_code', sa.String(length=100), nullable=True),
        sa.Column('shift_id', sa.Integer(), nullable=True),
        sa.Column('booking_date', sa.Date(), nullable=True),
        sa.Column('triggered_by', sa.String(length=50), nullable=False, server_default='vehicle_assignment'),
        sa.Column('total_employees', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('email_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('email_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sms_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sms_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('push_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('push_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('details', JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    op.create_index('ix_notification_logs_tenant_route', 'notification_logs', ['tenant_id', 'route_id'])
    op.create_index('ix_notification_logs_created_at', 'notification_logs', ['created_at'])
    op.create_index('ix_notification_logs_tenant_shift_date', 'notification_logs', ['tenant_id', 'shift_id', 'booking_date'])


def downgrade() -> None:
    op.drop_index('ix_notification_logs_tenant_shift_date', table_name='notification_logs')
    op.drop_index('ix_notification_logs_created_at', table_name='notification_logs')
    op.drop_index('ix_notification_logs_tenant_route', table_name='notification_logs')
    op.drop_table('notification_logs')
