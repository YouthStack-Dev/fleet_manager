"""Feature 20: Schedule Reminder Notifications.

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-05-20 10:00:00.000000

Changes
-------
1. bookings
   - ADD reminder_sent_at  TIMESTAMP NULL
     Stamped when the pre-trip push/SMS reminder is fired; NULL means
     no reminder sent yet.  Indexed for fast scheduler queries.

2. tenant_configs
   - ADD schedule_reminder_enabled  BOOLEAN NOT NULL DEFAULT FALSE
     Master on/off switch per tenant.
   - ADD schedule_reminder_minutes  INTEGER NOT NULL DEFAULT 30
     How many minutes before pickup time the reminder fires.

All ADD COLUMN operations are idempotent (_has_column guard).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision      = "l6m7n8o9p0q1"
down_revision = "k5l6m7n8o9p0"
branch_labels = None
depends_on    = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_column(bind, table_name: str, column_name: str) -> bool:
    cols = {c["name"] for c in inspect(bind).get_columns(table_name)}
    return column_name in cols


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade():
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. bookings — reminder timestamp
    # ------------------------------------------------------------------
    if not _has_column(bind, "bookings", "reminder_sent_at"):
        op.add_column(
            "bookings",
            sa.Column(
                "reminder_sent_at",
                sa.DateTime(),
                nullable=True,
                comment=(
                    "Timestamp when the pre-trip reminder push/SMS was sent. "
                    "NULL means no reminder has been sent yet."
                ),
            ),
        )
        # Index to make the scheduler's WHERE filter fast:
        #   WHERE reminder_sent_at IS NULL AND status = 'Scheduled' AND booking_date = today
        op.create_index(
            "ix_bookings_reminder_sent_at",
            "bookings",
            ["reminder_sent_at"],
        )

    # ------------------------------------------------------------------
    # 2. tenant_configs — reminder feature flags
    # ------------------------------------------------------------------
    if not _has_column(bind, "tenant_configs", "schedule_reminder_enabled"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "schedule_reminder_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
                comment="When TRUE, pre-trip reminder notifications are sent for this tenant.",
            ),
        )

    if not _has_column(bind, "tenant_configs", "schedule_reminder_minutes"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "schedule_reminder_minutes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("30"),
                comment="Minutes before estimated pickup time to send the reminder.",
            ),
        )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade():
    bind = op.get_bind()

    # tenant_configs
    for col in ("schedule_reminder_minutes", "schedule_reminder_enabled"):
        if _has_column(bind, "tenant_configs", col):
            op.drop_column("tenant_configs", col)

    # bookings
    try:
        op.drop_index("ix_bookings_reminder_sent_at", table_name="bookings")
    except Exception:
        pass  # index may not exist if migration was only partially applied

    if _has_column(bind, "bookings", "reminder_sent_at"):
        op.drop_column("bookings", "reminder_sent_at")
