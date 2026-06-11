"""add vehicle rate distance slabs

Revision ID: 20260611_rate_slabs
Revises: 20260611_costing
Create Date: 2026-06-11 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_rate_slabs"
down_revision = "20260611_costing"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table):
        return False
    return column in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table):
        return False
    return index_name in [idx["name"] for idx in sa.inspect(bind).get_indexes(table)]


def upgrade() -> None:
    if not _has_table("rate_card_distance_slabs"):
        op.create_table(
            "rate_card_distance_slabs",
            sa.Column("distance_slab_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("slot_id", sa.Integer(), sa.ForeignKey("rate_card_slots.slot_id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("min_km", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("max_km", sa.Numeric(10, 3), nullable=False),
            sa.Column("buffer_km", sa.Numeric(10, 3), nullable=False, server_default="0"),
            sa.Column("rate_per_km", sa.Numeric(12, 2), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_rate_card_distance_slabs_distance_slab_id", "rate_card_distance_slabs", ["distance_slab_id"])
        op.create_index("ix_rate_card_distance_slabs_slot_id", "rate_card_distance_slabs", ["slot_id"])
        op.create_index("ix_rate_card_distance_slabs_slot_active", "rate_card_distance_slabs", ["slot_id", "is_active"])
        op.create_index("ix_rate_card_distance_slabs_range", "rate_card_distance_slabs", ["slot_id", "min_km", "max_km"])


def downgrade() -> None:
    if _has_table("rate_card_distance_slabs"):
        op.drop_table("rate_card_distance_slabs")
