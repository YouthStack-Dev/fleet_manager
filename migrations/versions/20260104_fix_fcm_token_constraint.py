"""fix_fcm_token_constraint

Revision ID: fix_fcm_token_constraint
Revises: 20260103145959
Create Date: 2026-01-04 08:15:00

This migration fixes the FCM token constraint issue:
1. Drops the unique constraint/index on fcm_token
2. Makes fcm_token nullable (cleared on logout/expiry)
3. Creates a non-unique index for performance

Rationale:
- FCM tokens naturally reuse (same device = same token)
- Historical inactive sessions should preserve their original tokens
- The real constraint we need: one ACTIVE session per user per platform (already exists via uq_active_user_platform)
- Clearing tokens on logout keeps data clean and prevents confusion
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_fcm_token_constraint'
down_revision = '20260103145959'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Fix FCM token constraint:
    1. Drop unique index on fcm_token
    2. Make fcm_token nullable
    3. Create non-unique index on fcm_token
    4. Clear fcm_token for all inactive sessions (data cleanup)
    """
    
    # Step 1: Drop the unique index on fcm_token
    op.drop_index('idx_fcm_token', table_name='user_sessions')
    
    # Step 2: Make fcm_token nullable
    op.alter_column(
        'user_sessions',
        'fcm_token',
        existing_type=sa.String(length=255),
        nullable=True,
        comment='Firebase Cloud Messaging token (cleared on logout/expiry)'
    )
    
    # Step 3: Create non-unique index on fcm_token for fast lookups
    op.create_index(
        'idx_fcm_token',
        'user_sessions',
        ['fcm_token'],
        unique=False
    )
    
    # Step 4: Data cleanup - clear FCM tokens for all inactive sessions
    # This prevents any potential conflicts and makes it clear which tokens are active
    op.execute("""
        UPDATE user_sessions
        SET fcm_token = NULL
        WHERE is_active = FALSE
    """)


def downgrade() -> None:
    """
    Revert FCM token constraint changes (NOT RECOMMENDED)
    
    WARNING: This will fail if there are duplicate fcm_tokens in the table!
    Only use this if you're absolutely sure you want to go back.
    """
    
    # Drop non-unique index
    op.drop_index('idx_fcm_token', table_name='user_sessions')
    
    # Recreate unique index (will fail if duplicates exist)
    op.create_index(
        'idx_fcm_token',
        'user_sessions',
        ['fcm_token'],
        unique=True
    )
    
    # Make fcm_token non-nullable (will fail if any NULL values exist)
    op.alter_column(
        'user_sessions',
        'fcm_token',
        existing_type=sa.String(length=255),
        nullable=False,
        comment='Firebase Cloud Messaging token'
    )
