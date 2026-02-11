"""add_driver_android_device_management

Revision ID: 00a6c88b8420
Revises: 20260104_partial_idx
Create Date: 2026-02-11 15:06:24.115448

Purpose:
Add Android device management columns to drivers table for passwordless authentication.

Features:
- active_android_id: Currently active Android device ID (NO unique constraint to allow multi-vendor support)
- android_id_history: JSONB array storing all device login attempts with metadata

Security:
- Same license holder CAN use same Android ID across multiple vendor accounts
- Different license holders CANNOT use the same Android ID (enforced at application level)
- Index on active_android_id for query performance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '00a6c88b8420'
down_revision = '20260104_partial_idx'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add active_android_id column (nullable, indexed, NO unique constraint)
    # No unique constraint allows same person to use same device across multiple vendors
    op.add_column('drivers', sa.Column('active_android_id', sa.String(length=255), nullable=True))
    op.create_index('ix_drivers_active_android_id', 'drivers', ['active_android_id'], unique=False)
    
    # Add android_id_history column (JSONB, default empty array)
    # Stores complete history of device login attempts with timestamps
    op.add_column('drivers', sa.Column('android_id_history', postgresql.JSONB, nullable=False, server_default='[]'))


def downgrade() -> None:
    # Remove columns in reverse order
    op.drop_column('drivers', 'android_id_history')
    op.drop_index('ix_drivers_active_android_id', table_name='drivers')
    op.drop_column('drivers', 'active_android_id')
