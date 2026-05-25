"""add_chat_tables

Revision ID: 20260525_chat
Revises: 20260521_1300_add_dark_hour_boarding_mode
Create Date: 2026-05-25 10:00:00.000000

Creates two tables for the Employee ↔ Driver real-time chat feature:

  chat_sessions   — one row per booking (activated on booking assignment)
  chat_messages   — every message sent (employee / driver / system)

Real-time delivery: Firebase Realtime Database (handled in app code).
Permanent storage:  PostgreSQL (these tables — full audit trail).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision      = "20260525_chat"
down_revision = "o9p0q1r2s3t4"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── chat_sessions ─────────────────────────────────────────────────────
    op.create_table(
        "chat_sessions",

        sa.Column("id",         sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(50),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("bookings.booking_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("employees.employee_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("drivers.driver_id",   ondelete="SET NULL"),
            nullable=True,
        ),

        # Language preferences (ISO 639-1 — set by user in the mobile app)
        sa.Column("employee_language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("driver_language",   sa.String(10), nullable=False, server_default="en"),

        sa.Column("is_active",    sa.Boolean(),  nullable=False, server_default="true"),
        sa.Column("activated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at",   sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",   sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # one session per booking
    op.create_unique_constraint(
        "uq_chat_sessions_booking_id", "chat_sessions", ["booking_id"]
    )
    op.create_index("ix_chat_sessions_id",        "chat_sessions", ["id"])
    op.create_index("ix_chat_sessions_tenant_id", "chat_sessions", ["tenant_id"])
    op.create_index("ix_chat_sessions_booking_id","chat_sessions", ["booking_id"])

    # ── chat_messages ─────────────────────────────────────────────────────
    op.create_table(
        "chat_messages",

        sa.Column("id",        sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(50),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("bookings.booking_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("chat_sessions.id",   ondelete="CASCADE"),
            nullable=False,
        ),

        # "employee" | "driver" | "system"
        sa.Column("sender_type",       sa.String(20),  nullable=False),
        sa.Column("sender_id",         sa.Integer(),   nullable=True),   # null for system

        # Original content
        sa.Column("original_text",     sa.Text(),      nullable=False),
        sa.Column("original_language", sa.String(10),  nullable=False, server_default="en"),

        # Cached translations:  {"hi": "...", "ar": "..."}
        # Updated async ~1 second after send
        sa.Column("translated_texts",  sa.JSON(),      nullable=True, server_default="{}"),

        # Firebase RTDB push key — used to push translation patches back to RTDB
        sa.Column("firebase_message_id", sa.String(200), nullable=True),

        sa.Column("is_system_message", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at",        sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_id",         "chat_messages", ["id"])
    op.create_index("ix_chat_messages_tenant_id",  "chat_messages", ["tenant_id"])
    op.create_index("ix_chat_messages_booking_id", "chat_messages", ["booking_id"])
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    # Composite index for fast "latest N messages for booking" queries
    op.create_index(
        "ix_chat_messages_booking_created",
        "chat_messages",
        ["booking_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
