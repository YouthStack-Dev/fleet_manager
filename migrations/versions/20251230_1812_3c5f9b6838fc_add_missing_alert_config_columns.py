"""add_missing_alert_config_columns

Revision ID: 3c5f9b6838fc
Revises: 20251230_220942_alert_system
Create Date: 2025-12-30 18:12:44.357242

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = '3c5f9b6838fc'
down_revision = '20251230_220942_alert_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing columns to alert_configurations table
    op.add_column('alert_configurations', sa.Column('config_name', sa.String(length=200), nullable=False, server_default='Default Configuration'))
    op.add_column('alert_configurations', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('alert_configurations', sa.Column('applicable_alert_types', JSON(), nullable=True))
    op.add_column('alert_configurations', sa.Column('enable_escalation', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('alert_configurations', sa.Column('escalation_threshold_seconds', sa.Integer(), nullable=False, server_default='300'))
    op.add_column('alert_configurations', sa.Column('auto_close_false_alarm_seconds', sa.Integer(), nullable=True))
    op.add_column('alert_configurations', sa.Column('require_closure_notes', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('alert_configurations', sa.Column('enable_geofencing_alerts', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('alert_configurations', sa.Column('geofence_radius_meters', sa.Integer(), nullable=True, server_default='1000'))
    op.add_column('alert_configurations', sa.Column('priority', sa.Integer(), nullable=False, server_default='100'))
    op.add_column('alert_configurations', sa.Column('created_by', sa.String(length=100), nullable=True))
    op.add_column('alert_configurations', sa.Column('updated_by', sa.String(length=100), nullable=True))
    
    # Change notification_channels from ARRAY to JSON for compatibility
    op.execute('ALTER TABLE alert_configurations ALTER COLUMN notification_channels TYPE JSON USING notification_channels::text::json')
    
    # Drop the old auto_escalate_after_seconds column (replaced by escalation_threshold_seconds)
    op.drop_column('alert_configurations', 'auto_escalate_after_seconds')
    
    # Remove server_default from config_name after initial creation
    op.alter_column('alert_configurations', 'config_name', server_default=None)


def downgrade() -> None:
    # Revert changes
    op.add_column('alert_configurations', sa.Column('auto_escalate_after_seconds', sa.Integer(), nullable=False, server_default='300'))
    op.execute('ALTER TABLE alert_configurations ALTER COLUMN notification_channels TYPE text[] USING notification_channels::text[]')
    
    op.drop_column('alert_configurations', 'updated_by')
    op.drop_column('alert_configurations', 'created_by')
    op.drop_column('alert_configurations', 'priority')
    op.drop_column('alert_configurations', 'geofence_radius_meters')
    op.drop_column('alert_configurations', 'enable_geofencing_alerts')
    op.drop_column('alert_configurations', 'require_closure_notes')
    op.drop_column('alert_configurations', 'auto_close_false_alarm_seconds')
    op.drop_column('alert_configurations', 'escalation_threshold_seconds')
    op.drop_column('alert_configurations', 'enable_escalation')
    op.drop_column('alert_configurations', 'applicable_alert_types')
    op.drop_column('alert_configurations', 'description')
    op.drop_column('alert_configurations', 'config_name')

