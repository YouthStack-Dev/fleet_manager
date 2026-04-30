"""sync bookings schema with Booking model

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-04-30 20:15:00.000000

Ensures the bookings table includes all columns expected by the current
SQLAlchemy Booking model and booking routes.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "c7d8e9f0a1b2"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def _fk_exists(bind, table_name: str, constraint_name: str) -> bool:
    result = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.table_constraints
            WHERE constraint_type = 'FOREIGN KEY'
              AND table_name = :table_name
              AND constraint_name = :constraint_name
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    )
    return result.fetchone() is not None


def _index_exists(bind, index_name: str) -> bool:
    result = bind.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :index_name"),
        {"index_name": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "bookings"):
        return

    # Columns expected by app.models.booking.Booking
    if not _has_column(bind, "bookings", "employee_code"):
        op.add_column("bookings", sa.Column("employee_code", sa.String(length=50), nullable=True))

    if not _has_column(bind, "bookings", "team_id"):
        op.add_column("bookings", sa.Column("team_id", sa.Integer(), nullable=True))

    if not _has_column(bind, "bookings", "boarding_otp"):
        op.add_column("bookings", sa.Column("boarding_otp", sa.Integer(), nullable=True))

    if not _has_column(bind, "bookings", "deboarding_otp"):
        op.add_column("bookings", sa.Column("deboarding_otp", sa.Integer(), nullable=True))

    if not _has_column(bind, "bookings", "pickup_location"):
        op.add_column("bookings", sa.Column("pickup_location", sa.String(length=255), nullable=True))

    if not _has_column(bind, "bookings", "drop_location"):
        op.add_column("bookings", sa.Column("drop_location", sa.String(length=255), nullable=True))

    if not _has_column(bind, "bookings", "reason"):
        op.add_column("bookings", sa.Column("reason", sa.Text(), nullable=True))

    # Backfill employee_code before applying NOT NULL.
    if _has_column(bind, "bookings", "employee_code"):
        op.execute(
            sa.text(
                """
                UPDATE bookings b
                SET employee_code = COALESCE(NULLIF(e.employee_code, ''), b.employee_id::text)
                FROM employees e
                WHERE b.employee_id = e.employee_id
                  AND (b.employee_code IS NULL OR b.employee_code = '')
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE bookings
                SET employee_code = employee_id::text
                WHERE employee_code IS NULL OR employee_code = ''
                """
            )
        )
        op.alter_column(
            "bookings",
            "employee_code",
            existing_type=sa.String(),
            nullable=False,
        )

    if (
        _has_column(bind, "bookings", "team_id")
        and _has_table(bind, "teams")
        and not _fk_exists(bind, "bookings", "bookings_team_id_fkey")
    ):
        op.create_foreign_key(
            "bookings_team_id_fkey",
            "bookings",
            "teams",
            ["team_id"],
            ["team_id"],
            ondelete="SET NULL",
        )

    if _has_column(bind, "bookings", "team_id") and not _index_exists(bind, "ix_bookings_team_id"):
        op.create_index("ix_bookings_team_id", "bookings", ["team_id"])

    if _has_column(bind, "bookings", "employee_code") and not _index_exists(bind, "ix_bookings_employee_code"):
        op.create_index("ix_bookings_employee_code", "bookings", ["employee_code"])


def downgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "bookings"):
        return

    if _index_exists(bind, "ix_bookings_employee_code"):
        op.drop_index("ix_bookings_employee_code", table_name="bookings")

    if _index_exists(bind, "ix_bookings_team_id"):
        op.drop_index("ix_bookings_team_id", table_name="bookings")

    if _fk_exists(bind, "bookings", "bookings_team_id_fkey"):
        op.drop_constraint("bookings_team_id_fkey", "bookings", type_="foreignkey")

    for column_name in [
        "reason",
        "drop_location",
        "pickup_location",
        "deboarding_otp",
        "boarding_otp",
        "team_id",
        "employee_code",
    ]:
        if _has_column(bind, "bookings", column_name):
            op.drop_column("bookings", column_name)
