"""Add user_sessions table for unified push notification management

Revision ID: 20260103145959
Revises: 3c5f9b6838fc
Create Date: 2026-01-03 14:59:59.000000

This migration creates the user_sessions table for unified device session management
across all user types (admin, employee, vendor, driver) with optimized indexes for
high-performance push notification delivery.

Key Features:
- Single table for all user types (eliminates joins)
- One active session per user per platform (enforced by unique constraint)
- Platform-aware (web vs app)
- Optimized indexes matching query patterns
- Redis-ready for cache-first architecture
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260103145959'
down_revision = '3c5f9b6838fc'  # Points to add_missing_alert_config_columns
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create user_sessions table with all indexes and constraints
    """
    # Create user_sessions table
    op.create_table(
        'user_sessions',
        
        # Primary key
        sa.Column('session_id', sa.Integer(), autoincrement=True, nullable=False),
        
        # Universal user identification
        sa.Column('user_id', sa.Integer(), nullable=False, comment='ID from respective user table (admin/employee/vendor/driver)'),
        sa.Column('user_type', sa.String(length=20), nullable=False, comment='User type: admin, employee, vendor, driver'),
        sa.Column('tenant_id', sa.String(length=50), nullable=False, comment='Tenant/organization ID for multi-tenancy'),
        
        # Platform & device info
        sa.Column('platform', sa.String(length=10), nullable=False, comment='Platform: web or app'),
        sa.Column('device_type', sa.String(length=20), nullable=True, comment='Device type: ios, android, chrome, firefox, safari'),
        sa.Column('device_id', sa.String(length=100), nullable=True, comment='Unique device fingerprint for tracking'),
        
        # FCM token
        sa.Column('fcm_token', sa.String(length=255), nullable=True, comment='Firebase Cloud Messaging token (cleared on logout/expiry)'),
        
        # Session lifecycle
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='Active session flag'),
        sa.Column('last_activity_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'), comment='Last activity timestamp for session health'),
        sa.Column('expires_at', sa.DateTime(), nullable=True, comment='Session expiry (auto-set to now() + 30 days)'),
        
        # Metadata for debugging
        sa.Column('app_version', sa.String(length=20), nullable=True, comment='App version for compatibility tracking'),
        sa.Column('device_model', sa.String(length=100), nullable=True, comment='Device model (e.g., iPhone 14, Samsung Galaxy S23)'),
        sa.Column('ip_address', sa.String(length=45), nullable=True, comment='IP address (IPv4 or IPv6)'),
        sa.Column('user_agent', sa.Text(), nullable=True, comment='Browser/app user agent string'),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        
        # Primary key constraint
        sa.PrimaryKeyConstraint('session_id', name='pk_user_sessions'),
    )
    
    # Create partial unique index - only enforces uniqueness when is_active=TRUE
    # This allows multiple inactive sessions (history) but only ONE active session per user/platform
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_platform
        ON user_sessions (user_type, user_id, platform)
        WHERE is_active = TRUE;
    """)
    
    # Create optimized indexes for query patterns
    
    # Index for most common query: Get active session for user
    # Matches: WHERE user_type = ? AND user_id = ? AND is_active = TRUE
    op.create_index(
        'idx_user_active',
        'user_sessions',
        ['user_type', 'user_id', 'is_active'],
        unique=False
    )
    
    # Index for platform-specific lookup
    # Matches: WHERE user_type = ? AND user_id = ? AND platform = ? AND is_active = TRUE
    op.create_index(
        'idx_user_platform',
        'user_sessions',
        ['user_type', 'user_id', 'platform', 'is_active'],
        unique=False
    )
    
    # Index for tenant-level queries (admin dashboard, analytics)
    # Matches: WHERE tenant_id = ? AND is_active = TRUE
    op.create_index(
        'idx_tenant_active',
        'user_sessions',
        ['tenant_id', 'is_active'],
        unique=False
    )
    
    # Index for cleanup job (finds expired sessions efficiently)
    # Matches: WHERE is_active = TRUE AND expires_at < NOW()
    op.create_index(
        'idx_expires_at',
        'user_sessions',
        ['is_active', 'expires_at'],
        unique=False
    )
    
    # Non-unique index on fcm_token for faster lookups
    # Note: FCM tokens can appear in multiple sessions (active + historical inactive sessions)
    # The real uniqueness we enforce is: one ACTIVE session per user per platform (uq_active_user_platform)
    op.create_index(
        'idx_fcm_token',
        'user_sessions',
        ['fcm_token'],
        unique=False
    )
    
    # Create trigger for automatic updated_at timestamp update
    op.execute("""
        CREATE OR REPLACE FUNCTION update_user_sessions_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER trigger_update_user_sessions_updated_at
        BEFORE UPDATE ON user_sessions
        FOR EACH ROW
        EXECUTE FUNCTION update_user_sessions_updated_at();
    """)
    
    # Create function to auto-set expires_at on insert
    op.execute("""
        CREATE OR REPLACE FUNCTION set_session_expiry()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.expires_at IS NULL THEN
                NEW.expires_at = NOW() + INTERVAL '30 days';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER trigger_set_session_expiry
        BEFORE INSERT ON user_sessions
        FOR EACH ROW
        EXECUTE FUNCTION set_session_expiry();
    """)


def downgrade() -> None:
    """
    Drop user_sessions table and all related objects
    """
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS trigger_update_user_sessions_updated_at ON user_sessions")
    op.execute("DROP TRIGGER IF EXISTS trigger_set_session_expiry ON user_sessions")
    
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS update_user_sessions_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS set_session_expiry()")
    
    # Drop indexes (will be dropped automatically with table, but explicit for clarity)
    op.drop_index('idx_fcm_token', table_name='user_sessions')
    op.drop_index('idx_expires_at', table_name='user_sessions')
    op.drop_index('idx_tenant_active', table_name='user_sessions')
    op.drop_index('idx_user_platform', table_name='user_sessions')
    op.drop_index('idx_user_active', table_name='user_sessions')
    
    # Drop table
    op.drop_table('user_sessions')
