"""update shifts table structure

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-02 14:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c['name'] for c in insp.get_columns(table)]


def _has_constraint(table, constraint_name):
    bind = op.get_bind()
    insp = inspect(bind)
    constraints = insp.get_unique_constraints(table)
    return any(c['name'] == constraint_name for c in constraints)


def upgrade():
    # Remove old columns from shifts table (idempotent)
    if _has_column('shifts', 'name'):
        op.drop_column('shifts', 'name')
    if _has_column('shifts', 'start_time'):
        op.drop_column('shifts', 'start_time')
    if _has_column('shifts', 'end_time'):
        op.drop_column('shifts', 'end_time')

    # Add new columns to match the current Shift model (idempotent)
    if not _has_column('shifts', 'shift_code'):
        op.add_column('shifts', sa.Column('shift_code', sa.String(length=50), nullable=False, server_default='DEFAULT'))
        op.alter_column('shifts', 'shift_code', server_default=None)
    if not _has_column('shifts', 'log_type'):
        op.add_column('shifts', sa.Column('log_type', sa.String(length=20), nullable=False, server_default='IN'))
        op.alter_column('shifts', 'log_type', server_default=None)
    if not _has_column('shifts', 'shift_time'):
        op.add_column('shifts', sa.Column('shift_time', sa.Time(), nullable=False, server_default='09:00:00'))
        op.alter_column('shifts', 'shift_time', server_default=None)
    if not _has_column('shifts', 'pickup_type'):
        op.add_column('shifts', sa.Column('pickup_type', sa.String(length=20), nullable=True))
    if not _has_column('shifts', 'gender'):
        op.add_column('shifts', sa.Column('gender', sa.String(length=20), nullable=True))
    if not _has_column('shifts', 'waiting_time_minutes'):
        op.add_column('shifts', sa.Column('waiting_time_minutes', sa.Integer(), nullable=False, server_default='0'))
        op.alter_column('shifts', 'waiting_time_minutes', server_default=None)

    # Create unique constraint for shift_code per tenant (idempotent)
    if not _has_constraint('shifts', 'uq_shift_code_per_tenant'):
        op.create_unique_constraint('uq_shift_code_per_tenant', 'shifts', ['tenant_id', 'shift_code'])


def downgrade():
    if _has_constraint('shifts', 'uq_shift_code_per_tenant'):
        op.drop_constraint('uq_shift_code_per_tenant', 'shifts', type_='unique')
    if _has_column('shifts', 'waiting_time_minutes'):
        op.drop_column('shifts', 'waiting_time_minutes')
    if _has_column('shifts', 'gender'):
        op.drop_column('shifts', 'gender')
    if _has_column('shifts', 'pickup_type'):
        op.drop_column('shifts', 'pickup_type')
    if _has_column('shifts', 'shift_time'):
        op.drop_column('shifts', 'shift_time')
    if _has_column('shifts', 'log_type'):
        op.drop_column('shifts', 'log_type')
    if _has_column('shifts', 'shift_code'):
        op.drop_column('shifts', 'shift_code')

    # Restore old columns
    if not _has_column('shifts', 'name'):
        op.add_column('shifts', sa.Column('name', sa.String(length=100), nullable=False, server_default='default'))
        op.alter_column('shifts', 'name', server_default=None)
    if not _has_column('shifts', 'start_time'):
        op.add_column('shifts', sa.Column('start_time', sa.Time(), nullable=False, server_default='09:00:00'))
        op.alter_column('shifts', 'start_time', server_default=None)
    if not _has_column('shifts', 'end_time'):
        op.add_column('shifts', sa.Column('end_time', sa.Time(), nullable=False, server_default='18:00:00'))
        op.alter_column('shifts', 'end_time', server_default=None)
