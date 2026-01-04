"""fix_unique_constraint_partial

Revision ID: 20260104_fix_unique_constraint_partial
Revises: fix_fcm_token_constraint
Create Date: 2026-01-04 14:40:00

CRITICAL FIX: Make uq_active_user_platform a PARTIAL unique constraint

Problem:
- Current constraint: UNIQUE (user_type, user_id, platform, is_active)
- This prevents multiple INACTIVE sessions (only allows 1 inactive record per user/platform)
- Users need session history with multiple inactive records

Solution:
- Drop the regular unique constraint
- Create a PARTIAL unique index: UNIQUE WHERE is_active = TRUE
- This allows infinite inactive sessions but only ONE active session per user/platform
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260104_partial_idx'
down_revision = 'fix_fcm_token_constraint'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Replace regular unique constraint with partial unique index
    
    This allows:
    - Multiple inactive sessions (for history)
    - Only ONE active session per user per platform
    """
    
    # Step 1: Drop the existing unique constraint
    op.drop_constraint('uq_active_user_platform', 'user_sessions', type_='unique')
    
    # Step 2: Create a partial unique index (PostgreSQL specific)
    # This only enforces uniqueness when is_active = TRUE
    op.execute("""
        CREATE UNIQUE INDEX uq_active_user_platform
        ON user_sessions (user_type, user_id, platform)
        WHERE is_active = TRUE
    """)


def downgrade() -> None:
    """
    Revert to regular unique constraint (NOT RECOMMENDED)
    
    WARNING: This will fail if there are multiple inactive sessions!
    """
    
    # Drop partial unique index
    op.drop_index('uq_active_user_platform', table_name='user_sessions')
    
    # Recreate regular unique constraint (will fail if duplicates exist)
    op.create_unique_constraint(
        'uq_active_user_platform',
        'user_sessions',
        ['user_type', 'user_id', 'platform', 'is_active']
    )
