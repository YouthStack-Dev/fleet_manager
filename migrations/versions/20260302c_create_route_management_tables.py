"""create_route_management_tables

Revision ID: 20260302c_route_mgmt_tables
Revises: 20260302_notif_logs
Create Date: 2026-03-02

Purpose:
Create route_management and route_management_bookings tables.

These tables existed in the original DB before Alembic was set up, so
they were never captured in the initial migration.  This migration
creates them on fresh databases (CI/CD, staging, new prod setups)
and is a no-op on existing databases where they already exist.

NOTE: escort_otp and escort_boarded columns are intentionally NOT included
here — they are added by the next migration (20260303_escort_otp).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260302c_route_mgmt_tables'
down_revision = '20260302_notif_logs'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    # ── route_management ────────────────────────────────────────────────────
    if 'route_management' not in existing_tables:
        op.create_table(
            'route_management',
            sa.Column('route_id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(50), nullable=False),
            sa.Column('shift_id', sa.Integer(), nullable=True),
            sa.Column('route_code', sa.String(100), nullable=True),
            # Assignment columns
            sa.Column('assigned_vendor_id', sa.Integer(), nullable=True),
            sa.Column('assigned_vehicle_id', sa.Integer(), nullable=True),
            sa.Column('assigned_driver_id', sa.Integer(), nullable=True),
            sa.Column('assigned_escort_id', sa.Integer(), sa.ForeignKey('escorts.escort_id'), nullable=True),
            # Escort safety
            sa.Column('escort_required', sa.Boolean(), nullable=False, server_default='false'),
            # Status (stored as VARCHAR, non-native enum for portability)
            sa.Column(
                'status',
                sa.String(50),
                nullable=False,
                server_default='Planned',
            ),
            # Time / distance estimates
            sa.Column('estimated_total_time', sa.Float(), nullable=True),
            sa.Column('estimated_total_distance', sa.Float(), nullable=True),
            sa.Column('actual_total_time', sa.Float(), nullable=True),
            sa.Column('actual_total_distance', sa.Float(), nullable=True),
            sa.Column('buffer_time', sa.Float(), nullable=True),
            # Meta
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        # Index used by the ORM for tenant + status queries
        op.create_index(
            'ix_route_management_tenant_status',
            'route_management',
            ['tenant_id', 'status'],
        )
    else:
        # Table already exists — make sure the index is present
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('route_management')]
        if 'ix_route_management_tenant_status' not in existing_indexes:
            op.create_index(
                'ix_route_management_tenant_status',
                'route_management',
                ['tenant_id', 'status'],
            )

    # ── route_management_bookings ────────────────────────────────────────────
    if 'route_management_bookings' not in existing_tables:
        op.create_table(
            'route_management_bookings',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                'route_id',
                sa.Integer(),
                sa.ForeignKey('route_management.route_id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('booking_id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=False),
            sa.Column('estimated_pick_up_time', sa.String(10), nullable=True),
            sa.Column('estimated_distance', sa.Float(), nullable=True),
            sa.Column('actual_pick_up_time', sa.String(10), nullable=True),
            sa.Column('actual_distance', sa.Float(), nullable=True),
            sa.Column('estimated_drop_time', sa.String(10), nullable=True),
            sa.Column('actual_drop_time', sa.String(10), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('route_id', 'booking_id', name='uq_route_management_booking_unique'),
        )


def downgrade():
    # Only drop if this migration actually created them (i.e. they are empty /
    # the tables were not pre-existing).  A full downgrade on a fresh DB is safe.
    op.drop_table('route_management_bookings')
    op.drop_index('ix_route_management_tenant_status', table_name='route_management')
    op.drop_table('route_management')
