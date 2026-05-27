"""add_geofence_eta_columns

Revision ID: 20260527_geo
Revises: 20260527_dlh
Create Date: 2026-05-27 11:00:00.000000

Adds configuration and tracking columns for two Phase 4 features:

  IMP-7  Geofence arrival triggers
  ────────────────────────────────
  tenant_configs.geofence_arrival_radius_meters
    Radius (metres) within which the driver is considered "arriving" at a stop.
    Default 300 m.  Configurable per tenant.

  route_management_bookings.geofence_notified_at
    Timestamp (UTC) of when the "Driver arriving" FCM was sent for this stop.
    NULL = not yet notified.  Set once; never reset.  Prevents duplicate pushes.

  IMP-6  ETA recalculation from live location
  ────────────────────────────────────────────
  tenant_configs.eta_change_threshold_minutes
    Minimum ETA delta (minutes) before an updated estimate is pushed to the
    employee.  Default 5 min.  Prevents notification spam for tiny fluctuations.

  route_management_bookings.eta_updated_at
    Timestamp (UTC) of the last ETA update for this stop from a live GPS ping.
    NULL = ETA never updated by a live ping.  Used as a rate-limiter (no more
    than one ETA update per 2 minutes per stop).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision      = "20260527_geo"
down_revision = "20260527_dlh"
branch_labels = None
depends_on    = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade() -> None:
    # ── tenant_configs ────────────────────────────────────────────────────
    if not _has_column("tenant_configs", "geofence_arrival_radius_meters"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "geofence_arrival_radius_meters",
                sa.Integer(),
                nullable=False,
                server_default="300",
            ),
        )

    if not _has_column("tenant_configs", "eta_change_threshold_minutes"):
        op.add_column(
            "tenant_configs",
            sa.Column(
                "eta_change_threshold_minutes",
                sa.Integer(),
                nullable=False,
                server_default="5",
            ),
        )

    # ── route_management_bookings ─────────────────────────────────────────
    if not _has_column("route_management_bookings", "geofence_notified_at"):
        op.add_column(
            "route_management_bookings",
            sa.Column(
                "geofence_notified_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    if not _has_column("route_management_bookings", "eta_updated_at"):
        op.add_column(
            "route_management_bookings",
            sa.Column(
                "eta_updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_column("route_management_bookings", "eta_updated_at")
    op.drop_column("route_management_bookings", "geofence_notified_at")
    op.drop_column("tenant_configs", "eta_change_threshold_minutes")
    op.drop_column("tenant_configs", "geofence_arrival_radius_meters")
