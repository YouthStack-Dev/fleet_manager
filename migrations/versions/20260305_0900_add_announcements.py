"""add_announcements

Revision ID: 20260305_announcements
Revises: 20260304_merge_heads
Create Date: 2026-03-05 09:00:00.000000

Full announcement / broadcast feature.

Tables
──────
  announcements           — one row per admin-created broadcast
  announcement_recipients — per-user delivery tracking

Channels supported
──────────────────
  push   → FCM push notification
  sms    → Twilio SMS to recipient phone
  email  → SMTP email to recipient email
  in_app → in-app inbox (always persisted)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260305_announcements"
down_revision = "20260304_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── announcements ─────────────────────────────────────────────────────────
    op.create_table(
        "announcements",
        sa.Column("announcement_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(50),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),

        # Content
        sa.Column("title",            sa.String(200), nullable=False),
        sa.Column("body",             sa.Text(),      nullable=False),
        sa.Column("content_type",     sa.String(20),  nullable=False, server_default="text"),
        sa.Column("media_url",        sa.Text(),      nullable=True),
        sa.Column("media_filename",   sa.String(255), nullable=True),
        sa.Column("media_size_bytes", sa.Integer(),   nullable=True),

        # Targeting
        sa.Column("target_type", sa.String(30),  nullable=False),
        sa.Column("target_ids",  sa.JSON(),       nullable=True),

        # Delivery channels  e.g. ["push","sms","email","in_app"]
        sa.Column("channels", sa.JSON(), nullable=True),

        # Lifecycle
        sa.Column("status",       sa.String(20),  nullable=False, server_default="draft"),
        sa.Column("is_active",    sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("created_by",   sa.Integer(),   nullable=True),
        sa.Column("published_at", sa.DateTime(),  nullable=True),

        # Delivery counters
        sa.Column("total_recipients", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count",    sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count",    sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_device_count",  sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sms_sent_count",   sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_sent_count", sa.Integer(), nullable=False, server_default="0"),

        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_announcements_announcement_id", "announcements", ["announcement_id"])
    op.create_index("ix_announcements_tenant_id",       "announcements", ["tenant_id"])

    # ── announcement_recipients ───────────────────────────────────────────────
    op.create_table(
        "announcement_recipients",
        sa.Column("recipient_id",      sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "announcement_id",
            sa.Integer(),
            sa.ForeignKey("announcements.announcement_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_type",    sa.String(20),  nullable=False),
        sa.Column("recipient_user_id", sa.Integer(),   nullable=False),
        sa.Column("tenant_id",         sa.String(50),  nullable=False),
        sa.Column("delivery_status",   sa.String(20),  nullable=False, server_default="pending"),
        sa.Column("push_sent_at",      sa.DateTime(),  nullable=True),
        sa.Column("sms_sent_at",       sa.DateTime(),  nullable=True),
        sa.Column("email_sent_at",     sa.DateTime(),  nullable=True),
        sa.Column("read_at",           sa.DateTime(),  nullable=True),
        sa.Column("created_at",        sa.DateTime(),  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_announcement_recipients_recipient_id",      "announcement_recipients", ["recipient_id"])
    op.create_index("ix_announcement_recipients_announcement_id",   "announcement_recipients", ["announcement_id"])
    op.create_index("ix_announcement_recipients_recipient_user_id", "announcement_recipients", ["recipient_user_id"])
    op.create_index("ix_announcement_recipients_tenant_id",         "announcement_recipients", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("announcement_recipients")
    op.drop_table("announcements")
