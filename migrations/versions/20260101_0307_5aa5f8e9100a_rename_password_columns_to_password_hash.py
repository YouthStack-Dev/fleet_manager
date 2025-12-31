"""rename_password_columns_to_password_hash

Revision ID: 5aa5f8e9100a
Revises: 3c5f9b6838fc
Create Date: 2026-01-01 03:07:40.791220

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5aa5f8e9100a'
down_revision = '3c5f9b6838fc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename password column to password_hash for security compliance
    # This aligns database schema with application code expectations
    op.alter_column('employees', 'password', new_column_name='password_hash')
    op.alter_column('drivers', 'password', new_column_name='password_hash')
    op.alter_column('admin', 'password', new_column_name='password_hash')
    op.alter_column('vendor_users', 'password', new_column_name='password_hash')


def downgrade() -> None:
    # Revert password_hash back to password
    op.alter_column('employees', 'password_hash', new_column_name='password')
    op.alter_column('drivers', 'password_hash', new_column_name='password')
    op.alter_column('admin', 'password_hash', new_column_name='password')
    op.alter_column('vendor_users', 'password_hash', new_column_name='password')
