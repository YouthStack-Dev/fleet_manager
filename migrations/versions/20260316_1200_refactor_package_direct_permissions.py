"""refactor policy package to store permissions as JSON column

Instead of a junction table, permissions are stored as a JSON array
of permission_ids directly in the iam_policy_packages.permission_ids column.

Changes:
  1. Add permission_ids JSON column to iam_policy_packages (default [])
  2. Migrate existing permissions from the default policy into the new column
  3. Drop default_policy_id column and its FK from iam_policy_packages
  4. Delete _DefaultPolicy rows from iam_policies (existed only for package permissions)
  5. Drop package_id column and its FK from iam_policies

Revision ID: 20260316_pkg_direct_perms
Revises: 20260316_employee_app_active
Create Date: 2026-03-16 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260316_pkg_direct_perms"
down_revision = "20260316_employee_app_active"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add permission_ids JSON column directly on the package table
    op.add_column(
        "iam_policy_packages",
        sa.Column("permission_ids", sa.JSON(), nullable=False, server_default="[]"),
    )

    # 2. Migrate: copy permissions from each package's default policy into the new column
    op.execute("""
        UPDATE iam_policy_packages pkg
        SET permission_ids = (
            SELECT COALESCE(
                json_agg(pp.permission_id),
                '[]'::json
            )
            FROM iam_policy_permission pp
            WHERE pp.policy_id = pkg.default_policy_id
        )
        WHERE pkg.default_policy_id IS NOT NULL
    """)

    # 3. Drop FK constraint on default_policy_id
    op.drop_constraint("fk_package_default_policy", "iam_policy_packages", type_="foreignkey")

    # 4. Drop default_policy_id column
    op.drop_column("iam_policy_packages", "default_policy_id")

    # 5. Delete _DefaultPolicy rows (they existed only to hold package permissions)
    op.execute("""
        DELETE FROM iam_policies
        WHERE package_id IS NOT NULL
          AND is_system_policy = FALSE
    """)

    # 6. Drop package_id FK and column from iam_policies
    try:
        op.drop_constraint("iam_policies_package_id_fkey", "iam_policies", type_="foreignkey")
    except Exception:
        pass  # constraint name may differ
    try:
        op.drop_index("ix_iam_policies_package_id", table_name="iam_policies")
    except Exception:
        pass
    op.drop_column("iam_policies", "package_id")


def downgrade():
    # Restore package_id column on iam_policies
    op.add_column("iam_policies", sa.Column("package_id", sa.Integer(), nullable=True))
    op.create_index("ix_iam_policies_package_id", "iam_policies", ["package_id"])
    op.create_foreign_key(
        "iam_policies_package_id_fkey",
        "iam_policies", "iam_policy_packages",
        ["package_id"], ["package_id"],
        ondelete="CASCADE",
    )

    # Restore default_policy_id on iam_policy_packages
    op.add_column("iam_policy_packages", sa.Column("default_policy_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_package_default_policy",
        "iam_policy_packages", "iam_policies",
        ["default_policy_id"], ["policy_id"],
        ondelete="SET NULL",
        use_alter=True,
    )

    # Drop the permission_ids column (data loss on downgrade)
    op.drop_column("iam_policy_packages", "permission_ids")
