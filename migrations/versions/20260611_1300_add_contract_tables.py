"""add contract tables

Revision ID: 20260611_contracts
Revises: 20260611_remove_costing
Create Date: 2026-06-11 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_contracts"
down_revision = "20260611_remove_costing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("contract_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_type_id", sa.Integer(), nullable=False),
        sa.Column("cost_center_id", sa.Integer(), nullable=True),
        sa.Column("contract_name", sa.String(length=150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.vendor_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_type_id"], ["vehicle_types.vehicle_type_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("contract_id"),
        sa.UniqueConstraint("vendor_id", "contract_name", name="uq_vendor_contract_name"),
        sa.UniqueConstraint("vendor_id", "vehicle_type_id", name="uq_vendor_vehicle_type_contract"),
    )
    op.create_index("ix_contracts_contract_id", "contracts", ["contract_id"], unique=False)
    op.create_index("ix_contracts_vendor_active", "contracts", ["vendor_id", "is_active"], unique=False)

    op.create_table(
        "contract_slabs",
        sa.Column("slab_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("min_km", sa.Float(), nullable=False),
        sa.Column("max_km", sa.Float(), nullable=True),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("min_km >= 0", name="ck_contract_slabs_min_km_non_negative"),
        sa.CheckConstraint("max_km IS NULL OR max_km > min_km", name="ck_contract_slabs_max_gt_min"),
        sa.CheckConstraint("rate > 0", name="ck_contract_slabs_rate_positive"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.contract_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("slab_id"),
        sa.UniqueConstraint("contract_id", "min_km", name="uq_contract_slab_min_km"),
    )
    op.create_index("ix_contract_slabs_contract_active", "contract_slabs", ["contract_id", "is_active"], unique=False)
    op.create_index("ix_contract_slabs_slab_id", "contract_slabs", ["slab_id"], unique=False)

    op.add_column("vehicles", sa.Column("contract_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_vehicles_contract_id",
        "vehicles",
        "contracts",
        ["contract_id"],
        ["contract_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_vehicles_contract_id", "vehicles", type_="foreignkey")
    op.drop_column("vehicles", "contract_id")

    op.drop_index("ix_contract_slabs_slab_id", table_name="contract_slabs")
    op.drop_index("ix_contract_slabs_contract_active", table_name="contract_slabs")
    op.drop_table("contract_slabs")

    op.drop_index("ix_contracts_vendor_active", table_name="contracts")
    op.drop_index("ix_contracts_contract_id", table_name="contracts")
    op.drop_table("contracts")
