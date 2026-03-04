"""add_ride_review_system

Revision ID: 20260304_ride_reviews
Revises: 20260303_rm_booking_escort_otp
Create Date: 2026-03-04

Purpose:
Creates both tables needed for the ride review system in a single migration:

  ride_reviews   — stores optional post-ride reviews by employees
  review_tags    — admin-configurable word-tag bank (driver & vehicle tags)

ride_reviews features:
  - Overall trip rating (1-5 stars, optional)
  - Driver sub-review: stars + word-tags + free-text comment
  - Vehicle sub-review: stars + word-tags + free-text comment
  - All fields fully optional; one review per booking (unique constraint)
  - Star-rating CHECK constraints (1-5); indexed for fast lookup

review_tags features:
  - tenant_id = NULL  → global tag visible to all tenants
  - tenant_id = 'X'   → tag scoped to tenant X only
  - Admins add/remove tags via API with no redeployment
  - Employees may also submit any free-form custom word; no enforcement
  - Seeded with 9 driver tags + 9 vehicle tags on first run
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260304_ride_reviews'
down_revision = '20260303_rm_booking_escort_otp'
branch_labels = None
depends_on = None


# ── Seed data for review_tags ─────────────────────────────────────────────────
_DRIVER_TAGS = [
    ("Punctual",            0),
    ("Polite",              1),
    ("Safe Driver",         2),
    ("Helpful",             3),
    ("Professional",        4),
    ("Good Attitude",       5),
    ("Responsive",          6),
    ("Friendly",            7),
    ("Knowledgeable Route", 8),
]

_VEHICLE_TAGS = [
    ("Clean",           0),
    ("Comfortable",     1),
    ("Well Maintained", 2),
    ("AC Working",      3),
    ("Spacious",        4),
    ("Smooth Ride",     5),
    ("Good Music",      6),
    ("On Time",         7),
    ("Safe Vehicle",    8),
]


def upgrade():
    # ── 1. ride_reviews ───────────────────────────────────────────────────────
    op.create_table(
        'ride_reviews',
        sa.Column('review_id',       sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column('tenant_id',       sa.String(50), sa.ForeignKey('tenants.tenant_id',     ondelete='CASCADE'), nullable=False),
        sa.Column('booking_id',      sa.Integer(),  sa.ForeignKey('bookings.booking_id',   ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id',     sa.Integer(),  sa.ForeignKey('employees.employee_id', ondelete='CASCADE'), nullable=False),
        sa.Column('driver_id',       sa.Integer(),  sa.ForeignKey('drivers.driver_id',     ondelete='SET NULL'), nullable=True),
        sa.Column('vehicle_id',      sa.Integer(),  sa.ForeignKey('vehicles.vehicle_id',   ondelete='SET NULL'), nullable=True),
        sa.Column('route_id',        sa.Integer(),  nullable=True),
        sa.Column('overall_rating',  sa.Integer(),  nullable=True),
        sa.Column('driver_rating',   sa.Integer(),  nullable=True),
        sa.Column('driver_tags',     postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('driver_comment',  sa.Text(),     nullable=True),
        sa.Column('vehicle_rating',  sa.Integer(),  nullable=True),
        sa.Column('vehicle_tags',    postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('vehicle_comment', sa.Text(),     nullable=True),
        sa.Column('is_active',       sa.Boolean(),  nullable=False, server_default=sa.text('true')),
        sa.Column('created_at',      sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',      sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('booking_id', name='uq_ride_review_booking_id'),
        sa.CheckConstraint('overall_rating IS NULL OR (overall_rating >= 1 AND overall_rating <= 5)', name='ck_overall_rating'),
        sa.CheckConstraint('driver_rating  IS NULL OR (driver_rating  >= 1 AND driver_rating  <= 5)', name='ck_driver_rating'),
        sa.CheckConstraint('vehicle_rating IS NULL OR (vehicle_rating >= 1 AND vehicle_rating <= 5)', name='ck_vehicle_rating'),
    )
    op.create_index('ix_ride_reviews_tenant_id',   'ride_reviews', ['tenant_id'])
    op.create_index('ix_ride_reviews_booking_id',  'ride_reviews', ['booking_id'])
    op.create_index('ix_ride_reviews_employee_id', 'ride_reviews', ['employee_id'])
    op.create_index('ix_ride_reviews_driver_id',   'ride_reviews', ['driver_id'])
    op.create_index('ix_ride_reviews_vehicle_id',  'ride_reviews', ['vehicle_id'])

    # ── 2. review_tags ────────────────────────────────────────────────────────
    op.create_table(
        'review_tags',
        sa.Column('tag_id',        sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column('tenant_id',     sa.String(50),   sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=True),
        sa.Column('tag_type',      sa.String(20),   nullable=False),   # "driver" | "vehicle"
        sa.Column('tag_name',      sa.String(100),  nullable=False),
        sa.Column('display_order', sa.Integer(),    nullable=False, server_default=sa.text('0')),
        sa.Column('is_active',     sa.Boolean(),    nullable=False, server_default=sa.text('true')),
        sa.Column('created_at',    sa.DateTime(),   nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at',    sa.DateTime(),   nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_review_tags_tenant_id', 'review_tags', ['tenant_id'])
    op.create_index('ix_review_tags_tag_type',  'review_tags', ['tag_type'])
    op.create_index('ix_review_tags_is_active', 'review_tags', ['is_active'])

    # ── 3. Seed global tags (tenant_id = NULL → available to all tenants) ────
    op.bulk_insert(
        sa.table(
            'review_tags',
            sa.column('tenant_id',     sa.String),
            sa.column('tag_type',      sa.String),
            sa.column('tag_name',      sa.String),
            sa.column('display_order', sa.Integer),
            sa.column('is_active',     sa.Boolean),
        ),
        [
            {'tenant_id': None, 'tag_type': 'driver', 'tag_name': name, 'display_order': order, 'is_active': True}
            for name, order in _DRIVER_TAGS
        ] + [
            {'tenant_id': None, 'tag_type': 'vehicle', 'tag_name': name, 'display_order': order, 'is_active': True}
            for name, order in _VEHICLE_TAGS
        ],
    )


def downgrade():
    # Drop in reverse order (review_tags first — no dependents)
    op.drop_index('ix_review_tags_is_active', table_name='review_tags')
    op.drop_index('ix_review_tags_tag_type',  table_name='review_tags')
    op.drop_index('ix_review_tags_tenant_id', table_name='review_tags')
    op.drop_table('review_tags')

    op.drop_index('ix_ride_reviews_vehicle_id',  table_name='ride_reviews')
    op.drop_index('ix_ride_reviews_driver_id',   table_name='ride_reviews')
    op.drop_index('ix_ride_reviews_employee_id', table_name='ride_reviews')
    op.drop_index('ix_ride_reviews_booking_id',  table_name='ride_reviews')
    op.drop_index('ix_ride_reviews_tenant_id',   table_name='ride_reviews')
    op.drop_table('ride_reviews')
