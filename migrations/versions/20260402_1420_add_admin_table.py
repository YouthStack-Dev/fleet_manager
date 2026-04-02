"""add admin table

Revision ID: a1b2c3d4e5f6
Revises: 20260316_pkg_direct_perms
Create Date: 2026-04-02 14:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '20260316_pkg_direct_perms'
branch_labels = None
depends_on = None


def upgrade():
    # Create admin table
    op.create_table('admin',
        sa.Column('admin_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('email', sa.String(length=150), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('admin_id'),
        sa.ForeignKeyConstraint(['role_id'], ['iam_roles.role_id'], ondelete='CASCADE')
    )
    op.create_index(op.f('ix_admin_admin_id'), 'admin', ['admin_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_admin_admin_id'), table_name='admin')
    op.drop_table('admin')
