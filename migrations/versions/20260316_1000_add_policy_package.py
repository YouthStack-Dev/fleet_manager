"""add_policy_package

Revision ID: 20260316_policy_package
Revises: 20260305_announcements
Create Date: 2026-03-16 10:00:00.000000

Summary
───────
Introduces a per-tenant PolicyPackage — a container that groups tenant-scoped
policies together.  Each tenant has exactly one package.  Any policy that
belongs to a tenant is linked to that package via `package_id`.

The package holds a `default_policy_id` FK pointer (nullable, ON DELETE SET
NULL) that identifies the primary/main policy for the tenant.  This is the
canonical "pointer" pattern — the owner points to its selected child, not the
other way around.

Circular FK ordering
────────────────────
Because iam_policy_packages.default_policy_id → iam_policies and
iam_policies.package_id → iam_policy_packages form a cycle, we:
  1. Create iam_policy_packages WITHOUT the default_policy_id FK.
  2. Add package_id FK to iam_policies.
  3. Add default_policy_id column + FK constraint to iam_policy_packages
     via a separate ALTER TABLE, after iam_policies already exists.

Changes
───────
1. CREATE TABLE  iam_policy_packages  (no default_policy_id yet)
2. ALTER  TABLE  iam_policies          ADD COLUMN package_id  (FK)
3. ALTER  TABLE  iam_policy_packages   ADD COLUMN default_policy_id  (nullable FK)
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# ─── revision identifiers ────────────────────────────────────────────────────
revision = "20260316_policy_package"
down_revision = "20260305_announcements"
branch_labels = None
depends_on = None


# ─── upgrade ─────────────────────────────────────────────────────────────────
def upgrade() -> None:
    # 1. Create the policy packages table — WITHOUT default_policy_id yet.
    #    We add it in step 3 after iam_policies exists, to avoid a circular FK.
    op.create_table(
        "iam_policy_packages",
        sa.Column("package_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(50),
            sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False, server_default="Default Package"),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # 2. Add package_id FK to iam_policies (nullable — system policies have no package)
    op.add_column(
        "iam_policies",
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("iam_policy_packages.package_id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )

    # 3. Now that iam_policies exists, safely add the pointer column.
    #    ON DELETE SET NULL — if the default policy is deleted, the pointer
    #    automatically becomes NULL rather than violating a FK constraint.
    op.add_column(
        "iam_policy_packages",
        sa.Column("default_policy_id", sa.Integer(), nullable=True, index=True),
    )
    op.create_foreign_key(
        "fk_package_default_policy",          # constraint name
        "iam_policy_packages",                 # source table
        "iam_policies",                        # referent table
        ["default_policy_id"],                 # local cols
        ["policy_id"],                         # remote cols
        ondelete="SET NULL",
    )


# ─── downgrade ───────────────────────────────────────────────────────────────
def downgrade() -> None:
    # Drop in reverse order
    op.drop_constraint("fk_package_default_policy", "iam_policy_packages", type_="foreignkey")
    op.drop_column("iam_policy_packages", "default_policy_id")
    op.drop_column("iam_policies", "package_id")
    op.drop_table("iam_policy_packages")
