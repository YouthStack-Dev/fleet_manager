"""add_alert_system_tables

Revision ID: 20251230_220942_alert_system
Revises: 
Create Date: 2024-12-30 22:09:42.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, ARRAY


# revision identifiers, used by Alembic.
revision = '20251230_220942_alert_system'
down_revision = 'b75d731987dd'  # Connected to initial database schema
branch_labels = None
depends_on = None


def upgrade():
    # Create alerts table
    op.create_table(
        'alerts',
        sa.Column('alert_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=True),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('trigger_latitude', sa.Float(), nullable=False),
        sa.Column('trigger_longitude', sa.Float(), nullable=False),
        sa.Column('trigger_notes', sa.Text(), nullable=True),
        sa.Column('evidence_urls', JSON(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('acknowledged_by', sa.Integer(), nullable=True),
        sa.Column('acknowledged_by_name', sa.String(length=255), nullable=True),
        sa.Column('acknowledgment_notes', sa.Text(), nullable=True),
        sa.Column('estimated_arrival_minutes', sa.Integer(), nullable=True),
        sa.Column('response_time_seconds', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('closed_by', sa.Integer(), nullable=True),
        sa.Column('closed_by_name', sa.String(length=255), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('resolution_time_seconds', sa.Integer(), nullable=True),
        sa.Column('is_false_alarm', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('auto_escalated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('alert_metadata', JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('alert_id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.employee_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.booking_id'], ondelete='SET NULL'),
    )
    
    # Create indexes for alerts
    op.create_index('ix_alerts_tenant_id', 'alerts', ['tenant_id'])
    op.create_index('ix_alerts_employee_id', 'alerts', ['employee_id'])
    op.create_index('ix_alerts_booking_id', 'alerts', ['booking_id'])
    op.create_index('ix_alerts_status', 'alerts', ['status'])
    op.create_index('ix_alerts_triggered_at', 'alerts', ['triggered_at'])
    op.create_index('ix_alerts_tenant_status', 'alerts', ['tenant_id', 'status'])
    
    # Create alert_escalations table
    op.create_table(
        'alert_escalations',
        sa.Column('escalation_id', sa.Integer(), nullable=False),
        sa.Column('alert_id', sa.Integer(), nullable=False),
        sa.Column('escalation_level', sa.Integer(), nullable=False),
        sa.Column('escalated_at', sa.DateTime(), nullable=False),
        sa.Column('escalated_to_recipients', JSON(), nullable=False),
        sa.Column('escalation_reason', sa.Text(), nullable=True),
        sa.Column('is_automatic', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('escalation_id'),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.alert_id'], ondelete='CASCADE'),
    )
    
    # Create indexes for alert_escalations
    op.create_index('ix_alert_escalations_alert_id', 'alert_escalations', ['alert_id'])
    op.create_index('ix_alert_escalations_escalated_at', 'alert_escalations', ['escalated_at'])
    
    # Create alert_notifications table
    op.create_table(
        'alert_notifications',
        sa.Column('notification_id', sa.Integer(), nullable=False),
        sa.Column('alert_id', sa.Integer(), nullable=False),
        sa.Column('recipient_name', sa.String(length=255), nullable=True),
        sa.Column('recipient_email', sa.String(length=255), nullable=True),
        sa.Column('recipient_phone', sa.String(length=20), nullable=True),
        sa.Column('recipient_role', sa.String(length=50), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('subject', sa.String(length=500), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('notification_id'),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.alert_id'], ondelete='CASCADE'),
    )
    
    # Create indexes for alert_notifications
    op.create_index('ix_alert_notifications_alert_id', 'alert_notifications', ['alert_id'])
    op.create_index('ix_alert_notifications_status', 'alert_notifications', ['status'])
    op.create_index('ix_alert_notifications_channel', 'alert_notifications', ['channel'])
    
    # Create alert_configurations table
    op.create_table(
        'alert_configurations',
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('primary_recipients', JSON(), nullable=False),
        sa.Column('escalation_recipients', JSON(), nullable=True),
        sa.Column('auto_escalate_after_seconds', sa.Integer(), nullable=False, server_default='300'),
        sa.Column('notification_channels', ARRAY(sa.String()), nullable=False),
        sa.Column('emergency_contacts', JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_on_escalation', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_on_status_change', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('config_id'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ondelete='CASCADE'),
    )
    
    # Create indexes for alert_configurations
    op.create_index('ix_alert_configurations_tenant_id', 'alert_configurations', ['tenant_id'])
    op.create_index('ix_alert_configurations_team_id', 'alert_configurations', ['team_id'])
    op.create_index('ix_alert_configurations_tenant_team', 'alert_configurations', ['tenant_id', 'team_id'], unique=True)


def downgrade():
    # Drop alert_configurations table
    op.drop_index('ix_alert_configurations_tenant_team', table_name='alert_configurations')
    op.drop_index('ix_alert_configurations_team_id', table_name='alert_configurations')
    op.drop_index('ix_alert_configurations_tenant_id', table_name='alert_configurations')
    op.drop_table('alert_configurations')
    
    # Drop alert_notifications table
    op.drop_index('ix_alert_notifications_channel', table_name='alert_notifications')
    op.drop_index('ix_alert_notifications_status', table_name='alert_notifications')
    op.drop_index('ix_alert_notifications_alert_id', table_name='alert_notifications')
    op.drop_table('alert_notifications')
    
    # Drop alert_escalations table
    op.drop_index('ix_alert_escalations_escalated_at', table_name='alert_escalations')
    op.drop_index('ix_alert_escalations_alert_id', table_name='alert_escalations')
    op.drop_table('alert_escalations')
    
    # Drop alerts table
    op.drop_index('ix_alerts_tenant_status', table_name='alerts')
    op.drop_index('ix_alerts_triggered_at', table_name='alerts')
    op.drop_index('ix_alerts_status', table_name='alerts')
    op.drop_index('ix_alerts_booking_id', table_name='alerts')
    op.drop_index('ix_alerts_employee_id', table_name='alerts')
    op.drop_index('ix_alerts_tenant_id', table_name='alerts')
    op.drop_table('alerts')
