"""merge_escort_password_and_ride_reviews

Revision ID: 20260304_merge_heads
Revises: 20260303_add_escort_password, 20260304_ride_reviews
Create Date: 2026-03-04

Purpose:
-------
Merge migration that re-unifies two branches that both forked off from
20260303_rm_booking_escort_otp:

  Branch A → 20260303_add_escort_password
    Adds `escorts.password` (VARCHAR 64, nullable) for mobile-app auth.

  Branch B → 20260304_ride_reviews
    Creates `ride_reviews` + `review_tags` tables for the post-ride
    feedback system.

These two branches are completely independent — they touch different
tables and have no conflicting DDL — so the merge is a no-op (empty
upgrade/downgrade). After this revision Alembic will have a single
linear head again.
"""
from alembic import op
import sqlalchemy as sa

# Each entry in the tuple is one of the two branch heads being merged.
revision = '20260304_merge_heads'
down_revision = ('20260303_add_escort_password', '20260304_ride_reviews')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No DDL needed — both branches already applied their own changes.
    pass


def downgrade() -> None:
    # No DDL needed — rolling back is handled by each branch's own
    # downgrade() function.
    pass
