"""sync audit_logs schema with model

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-04-30 21:45:00.000000

Brings legacy audit_logs table (id/timestamp/changes...) in line with current
AuditLog model (audit_id/created_at/module/audit_data).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d1e2f3a4b5c6"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspect(bind).get_columns(table_name)}


def _index_exists(bind, index_name: str) -> bool:
    result = bind.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :index_name"),
        {"index_name": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "audit_logs"):
        return

    # id -> audit_id (PK)
    if _has_column(bind, "audit_logs", "id") and not _has_column(bind, "audit_logs", "audit_id"):
        op.execute(sa.text("ALTER TABLE audit_logs RENAME COLUMN id TO audit_id"))

    # timestamp -> created_at
    if _has_column(bind, "audit_logs", "timestamp") and not _has_column(bind, "audit_logs", "created_at"):
        op.execute(sa.text("ALTER TABLE audit_logs RENAME COLUMN \"timestamp\" TO created_at"))

    # changes -> audit_data
    if _has_column(bind, "audit_logs", "changes") and not _has_column(bind, "audit_logs", "audit_data"):
        op.execute(sa.text("ALTER TABLE audit_logs RENAME COLUMN changes TO audit_data"))

    # Add module column with safe default for existing rows
    if not _has_column(bind, "audit_logs", "module"):
        op.add_column(
            "audit_logs",
            sa.Column("module", sa.String(length=50), nullable=False, server_default="legacy"),
        )
        op.alter_column("audit_logs", "module", server_default=None)

    # Ensure created_at has default now()
    if _has_column(bind, "audit_logs", "created_at"):
        op.execute(sa.text("ALTER TABLE audit_logs ALTER COLUMN created_at SET DEFAULT now()"))

    # Drop legacy columns not used by current model
    for legacy_col in ["user_id", "user_type", "action", "resource_type", "resource_id", "ip_address"]:
        if _has_column(bind, "audit_logs", legacy_col):
            op.drop_column("audit_logs", legacy_col)

    # Ensure required columns are not null
    if _has_column(bind, "audit_logs", "tenant_id"):
        op.execute(sa.text("ALTER TABLE audit_logs ALTER COLUMN tenant_id SET NOT NULL"))
    if _has_column(bind, "audit_logs", "module"):
        op.execute(sa.text("ALTER TABLE audit_logs ALTER COLUMN module SET NOT NULL"))
    if _has_column(bind, "audit_logs", "audit_data"):
        op.execute(sa.text("ALTER TABLE audit_logs ALTER COLUMN audit_data SET NOT NULL"))
    if _has_column(bind, "audit_logs", "created_at"):
        op.execute(sa.text("ALTER TABLE audit_logs ALTER COLUMN created_at SET NOT NULL"))

    # Indexes aligned with model
    if not _index_exists(bind, "idx_tenant_module"):
        op.create_index("idx_tenant_module", "audit_logs", ["tenant_id", "module"])

    if not _index_exists(bind, "idx_module_created"):
        op.create_index("idx_module_created", "audit_logs", ["module", "created_at"])

    if not _index_exists(bind, "ix_audit_logs_created_at"):
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "audit_logs"):
        return

    if _index_exists(bind, "ix_audit_logs_created_at"):
        op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    if _index_exists(bind, "idx_module_created"):
        op.drop_index("idx_module_created", table_name="audit_logs")
    if _index_exists(bind, "idx_tenant_module"):
        op.drop_index("idx_tenant_module", table_name="audit_logs")

    # This downgrade restores legacy columns minimally.
    if not _has_column(bind, "audit_logs", "changes") and _has_column(bind, "audit_logs", "audit_data"):
        op.execute(sa.text("ALTER TABLE audit_logs RENAME COLUMN audit_data TO changes"))

    if not _has_column(bind, "audit_logs", "timestamp") and _has_column(bind, "audit_logs", "created_at"):
        op.execute(sa.text("ALTER TABLE audit_logs RENAME COLUMN created_at TO \"timestamp\""))

    if not _has_column(bind, "audit_logs", "id") and _has_column(bind, "audit_logs", "audit_id"):
        op.execute(sa.text("ALTER TABLE audit_logs RENAME COLUMN audit_id TO id"))

    if _has_column(bind, "audit_logs", "module"):
        op.drop_column("audit_logs", "module")

    for legacy_col, col_type in [
        ("user_id", sa.Integer()),
        ("user_type", sa.String(length=50)),
        ("action", sa.String(length=100)),
        ("resource_type", sa.String(length=100)),
        ("resource_id", sa.String(length=100)),
        ("ip_address", sa.String(length=50)),
    ]:
        if not _has_column(bind, "audit_logs", legacy_col):
            op.add_column("audit_logs", sa.Column(legacy_col, col_type, nullable=True))
