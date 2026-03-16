"""add is_app_active to employees

Revision ID: 20260316_employee_app_active
Revises: 20260316_policy_package
Create Date: 2026-03-16 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260316_employee_app_active"
down_revision = "20260316_policy_package"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "employees",
        sa.Column(
            "is_app_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade():
    op.drop_column("employees", "is_app_active")
