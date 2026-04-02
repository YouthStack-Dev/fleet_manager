"""comprehensive schema fix - missing tables and columns

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f7
Create Date: 2026-04-02 15:10:00.000000

Fixes:
  - vendors: add vendor_code, phone; drop old columns; fix constraints
  - drivers: rename license_expiry→license_expiry_date; add many missing columns; fix constraints
  - vehicles: add all document columns; fix per-vendor unique constraints
  - vehicle_types: add description, is_active; add unique constraint
  - employees: rename unique constraints; add uq_employee_code_per_tenant
  - CREATE vendor_users table (was never in any migration)
  - CREATE weekoff_configs table (was never in any migration)
  - CREATE cutoffs table (was never in any migration)
  - CREATE tenant_configs table (was never in any migration)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a3b4c5d6e7f8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    # ──────────────────────────────────────────────
    # 1. VENDORS TABLE
    # ──────────────────────────────────────────────
    # Drop old columns not in the current model
    op.drop_column('vendors', 'contact_person')
    op.drop_column('vendors', 'contact_number')
    op.drop_column('vendors', 'address')

    # Add new columns (vendor_code is NOT NULL - add with server_default, remove after)
    op.add_column('vendors', sa.Column('vendor_code', sa.String(50), nullable=False, server_default='UNKNOWN'))
    op.add_column('vendors', sa.Column('phone', sa.String(20), nullable=True))
    op.alter_column('vendors', 'vendor_code', server_default=None)

    # Add unique constraints
    op.create_unique_constraint('uq_vendor_name_per_tenant', 'vendors', ['tenant_id', 'name'])
    op.create_unique_constraint('uq_vendor_code_per_tenant', 'vendors', ['tenant_id', 'vendor_code'])
    op.create_unique_constraint('uq_vendor_email_per_tenant', 'vendors', ['tenant_id', 'email'])
    op.create_unique_constraint('uq_vendor_phone_per_tenant', 'vendors', ['tenant_id', 'phone'])

    # ──────────────────────────────────────────────
    # 2. DRIVERS TABLE
    # ──────────────────────────────────────────────
    # Rename license_expiry → license_expiry_date
    op.alter_column('drivers', 'license_expiry', new_column_name='license_expiry_date')

    # Drop old unique constraints
    op.drop_constraint('uq_driver_tenant_phone', 'drivers', type_='unique')
    op.drop_constraint('uq_driver_tenant_email', 'drivers', type_='unique')

    # Add missing columns (all nullable since adding to existing table)
    op.add_column('drivers', sa.Column('code', sa.String(50), nullable=True))
    op.add_column('drivers', sa.Column('gender', sa.String(20), nullable=True))
    op.add_column('drivers', sa.Column('date_of_birth', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('date_of_joining', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('permanent_address', sa.Text(), nullable=True))
    op.add_column('drivers', sa.Column('current_address', sa.Text(), nullable=True))
    op.add_column('drivers', sa.Column('photo_url', sa.Text(), nullable=True))

    # Background verification
    op.add_column('drivers', sa.Column('bg_verify_status', sa.String(20), nullable=True))
    op.add_column('drivers', sa.Column('bg_expiry_date', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('bg_verify_url', sa.Text(), nullable=True))

    # Police verification
    op.add_column('drivers', sa.Column('police_verify_status', sa.String(20), nullable=True))
    op.add_column('drivers', sa.Column('police_expiry_date', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('police_verify_url', sa.Text(), nullable=True))

    # Medical verification
    op.add_column('drivers', sa.Column('medical_verify_status', sa.String(20), nullable=True))
    op.add_column('drivers', sa.Column('medical_expiry_date', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('medical_verify_url', sa.Text(), nullable=True))

    # Training verification
    op.add_column('drivers', sa.Column('training_verify_status', sa.String(20), nullable=True))
    op.add_column('drivers', sa.Column('training_expiry_date', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('training_verify_url', sa.Text(), nullable=True))

    # Eye verification
    op.add_column('drivers', sa.Column('eye_verify_status', sa.String(20), nullable=True))
    op.add_column('drivers', sa.Column('eye_expiry_date', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('eye_verify_url', sa.Text(), nullable=True))

    # License info (license_expiry already renamed above)
    op.add_column('drivers', sa.Column('license_url', sa.Text(), nullable=True))

    # Badge info
    op.add_column('drivers', sa.Column('badge_number', sa.String(100), nullable=True))
    op.add_column('drivers', sa.Column('badge_expiry_date', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('badge_url', sa.Text(), nullable=True))

    # Alternate government ID
    op.add_column('drivers', sa.Column('alt_govt_id_number', sa.String(20), nullable=True))
    op.add_column('drivers', sa.Column('alt_govt_id_type', sa.String(50), nullable=True))
    op.add_column('drivers', sa.Column('alt_govt_id_url', sa.Text(), nullable=True))

    # Induction
    op.add_column('drivers', sa.Column('induction_date', sa.Date(), nullable=True))
    op.add_column('drivers', sa.Column('induction_url', sa.Text(), nullable=True))

    # Re-add unique constraints with correct names
    op.create_unique_constraint('uq_driver_tenant_email', 'drivers', ['tenant_id', 'email'])
    op.create_unique_constraint('uq_driver_tenant_phone', 'drivers', ['tenant_id', 'phone'])
    op.create_unique_constraint('uq_driver_code_per_vendor', 'drivers', ['vendor_id', 'code'])
    op.create_unique_constraint('uq_driver_tenant_license', 'drivers', ['tenant_id', 'license_number'])
    op.create_unique_constraint('uq_driver_tenant_badge', 'drivers', ['tenant_id', 'badge_number'])
    op.create_unique_constraint('uq_driver_tenant_alt_govt_id', 'drivers', ['tenant_id', 'alt_govt_id_number'])

    # ──────────────────────────────────────────────
    # 3. VEHICLES TABLE
    # ──────────────────────────────────────────────
    # Drop old global unique constraint
    op.drop_constraint('uq_vehicle_rc_number', 'vehicles', type_='unique')

    # Add all missing document columns
    op.add_column('vehicles', sa.Column('rc_expiry_date', sa.Date(), nullable=True))
    op.add_column('vehicles', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('vehicles', sa.Column('puc_number', sa.String(100), nullable=True))
    op.add_column('vehicles', sa.Column('puc_expiry_date', sa.Date(), nullable=True))
    op.add_column('vehicles', sa.Column('puc_url', sa.Text(), nullable=True))
    op.add_column('vehicles', sa.Column('fitness_number', sa.String(100), nullable=True))
    op.add_column('vehicles', sa.Column('fitness_expiry_date', sa.Date(), nullable=True))
    op.add_column('vehicles', sa.Column('fitness_url', sa.Text(), nullable=True))
    op.add_column('vehicles', sa.Column('tax_receipt_number', sa.String(100), nullable=True))
    op.add_column('vehicles', sa.Column('tax_receipt_date', sa.Date(), nullable=True))
    op.add_column('vehicles', sa.Column('tax_receipt_url', sa.Text(), nullable=True))
    op.add_column('vehicles', sa.Column('insurance_number', sa.String(100), nullable=True))
    op.add_column('vehicles', sa.Column('insurance_expiry_date', sa.Date(), nullable=True))
    op.add_column('vehicles', sa.Column('insurance_url', sa.Text(), nullable=True))
    op.add_column('vehicles', sa.Column('permit_number', sa.String(100), nullable=True))
    op.add_column('vehicles', sa.Column('permit_expiry_date', sa.Date(), nullable=True))
    op.add_column('vehicles', sa.Column('permit_url', sa.Text(), nullable=True))

    # Add per-vendor unique constraints (matching model's __table_args__)
    op.create_unique_constraint('uq_vendor_rc_number', 'vehicles', ['vendor_id', 'rc_number'])
    op.create_unique_constraint('uq_vendor_puc_number', 'vehicles', ['vendor_id', 'puc_number'])
    op.create_unique_constraint('uq_vendor_fitness_number', 'vehicles', ['vendor_id', 'fitness_number'])
    op.create_unique_constraint('uq_vendor_tax_receipt_number', 'vehicles', ['vendor_id', 'tax_receipt_number'])
    op.create_unique_constraint('uq_vendor_insurance_number', 'vehicles', ['vendor_id', 'insurance_number'])
    op.create_unique_constraint('uq_vendor_permit_number', 'vehicles', ['vendor_id', 'permit_number'])

    # ──────────────────────────────────────────────
    # 4. VEHICLE_TYPES TABLE
    # ──────────────────────────────────────────────
    op.add_column('vehicle_types', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('vehicle_types', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.alter_column('vehicle_types', 'is_active', server_default=None)
    op.create_unique_constraint('uq_vendor_vehicle_type_name', 'vehicle_types', ['vendor_id', 'name'])

    # ──────────────────────────────────────────────
    # 5. EMPLOYEES TABLE - rename constraints
    # ──────────────────────────────────────────────
    op.drop_constraint('uq_employee_tenant_phone', 'employees', type_='unique')
    op.drop_constraint('uq_employee_tenant_email', 'employees', type_='unique')
    op.create_unique_constraint('uq_employee_phone_per_tenant', 'employees', ['tenant_id', 'phone'])
    op.create_unique_constraint('uq_employee_email_per_tenant', 'employees', ['tenant_id', 'email'])
    op.create_unique_constraint('uq_employee_code_per_tenant', 'employees', ['tenant_id', 'employee_code'])

    # ──────────────────────────────────────────────
    # 6. CREATE vendor_users TABLE (never existed in migrations)
    # ──────────────────────────────────────────────
    op.create_table(
        'vendor_users',
        sa.Column('vendor_user_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('email', sa.String(150), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('password', sa.String(255), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('vendor_user_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['iam_roles.role_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_tenant_vendor_email'),
        sa.UniqueConstraint('tenant_id', 'phone', name='uq_tenant_vendor_phone'),
    )

    # ──────────────────────────────────────────────
    # 7. CREATE weekoff_configs TABLE (never existed in migrations)
    # ──────────────────────────────────────────────
    op.create_table(
        'weekoff_configs',
        sa.Column('weekoff_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('monday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tuesday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('wednesday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('thursday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('friday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('saturday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sunday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('weekoff_id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.employee_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('employee_id', name='uq_weekoff_employee'),
    )

    # ──────────────────────────────────────────────
    # 8. CREATE cutoffs TABLE (never existed in migrations)
    # ──────────────────────────────────────────────
    op.create_table(
        'cutoffs',
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('booking_login_cutoff', sa.Interval(), nullable=False, server_default='0'),
        sa.Column('cancel_login_cutoff', sa.Interval(), nullable=False, server_default='0'),
        sa.Column('booking_logout_cutoff', sa.Interval(), nullable=False, server_default='0'),
        sa.Column('cancel_logout_cutoff', sa.Interval(), nullable=False, server_default='0'),
        sa.Column('medical_emergency_booking_cutoff', sa.Interval(), nullable=False, server_default='0'),
        sa.Column('adhoc_booking_cutoff', sa.Interval(), nullable=False, server_default='0'),
        sa.Column('allow_adhoc_booking', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('allow_medical_emergency_booking', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('escort_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('tenant_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
    )

    # ──────────────────────────────────────────────
    # 9. CREATE tenant_configs TABLE (never existed in migrations)
    # ──────────────────────────────────────────────
    op.create_table(
        'tenant_configs',
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('escort_required_start_time', sa.Time(), nullable=True),
        sa.Column('escort_required_end_time', sa.Time(), nullable=True),
        sa.Column('escort_required_for_women', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('login_boarding_otp', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('login_deboarding_otp', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('logout_boarding_otp', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('logout_deboarding_otp', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('tenant_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
    )


def downgrade():
    # Drop new tables
    op.drop_table('tenant_configs')
    op.drop_table('cutoffs')
    op.drop_table('weekoff_configs')
    op.drop_table('vendor_users')

    # Revert employees constraints
    op.drop_constraint('uq_employee_code_per_tenant', 'employees', type_='unique')
    op.drop_constraint('uq_employee_email_per_tenant', 'employees', type_='unique')
    op.drop_constraint('uq_employee_phone_per_tenant', 'employees', type_='unique')
    op.create_unique_constraint('uq_employee_tenant_phone', 'employees', ['tenant_id', 'phone'])
    op.create_unique_constraint('uq_employee_tenant_email', 'employees', ['tenant_id', 'email'])

    # Revert vehicle_types
    op.drop_constraint('uq_vendor_vehicle_type_name', 'vehicle_types', type_='unique')
    op.drop_column('vehicle_types', 'is_active')
    op.drop_column('vehicle_types', 'description')

    # Revert vehicles
    op.drop_constraint('uq_vendor_permit_number', 'vehicles', type_='unique')
    op.drop_constraint('uq_vendor_insurance_number', 'vehicles', type_='unique')
    op.drop_constraint('uq_vendor_tax_receipt_number', 'vehicles', type_='unique')
    op.drop_constraint('uq_vendor_fitness_number', 'vehicles', type_='unique')
    op.drop_constraint('uq_vendor_puc_number', 'vehicles', type_='unique')
    op.drop_constraint('uq_vendor_rc_number', 'vehicles', type_='unique')
    op.drop_column('vehicles', 'permit_url')
    op.drop_column('vehicles', 'permit_expiry_date')
    op.drop_column('vehicles', 'permit_number')
    op.drop_column('vehicles', 'insurance_url')
    op.drop_column('vehicles', 'insurance_expiry_date')
    op.drop_column('vehicles', 'insurance_number')
    op.drop_column('vehicles', 'tax_receipt_url')
    op.drop_column('vehicles', 'tax_receipt_date')
    op.drop_column('vehicles', 'tax_receipt_number')
    op.drop_column('vehicles', 'fitness_url')
    op.drop_column('vehicles', 'fitness_expiry_date')
    op.drop_column('vehicles', 'fitness_number')
    op.drop_column('vehicles', 'puc_url')
    op.drop_column('vehicles', 'puc_expiry_date')
    op.drop_column('vehicles', 'puc_number')
    op.drop_column('vehicles', 'description')
    op.drop_column('vehicles', 'rc_expiry_date')
    op.create_unique_constraint('uq_vehicle_rc_number', 'vehicles', ['rc_number'])

    # Revert drivers
    op.drop_constraint('uq_driver_tenant_alt_govt_id', 'drivers', type_='unique')
    op.drop_constraint('uq_driver_tenant_badge', 'drivers', type_='unique')
    op.drop_constraint('uq_driver_tenant_license', 'drivers', type_='unique')
    op.drop_constraint('uq_driver_code_per_vendor', 'drivers', type_='unique')
    op.drop_constraint('uq_driver_tenant_phone', 'drivers', type_='unique')
    op.drop_constraint('uq_driver_tenant_email', 'drivers', type_='unique')
    op.drop_column('drivers', 'induction_url')
    op.drop_column('drivers', 'induction_date')
    op.drop_column('drivers', 'alt_govt_id_url')
    op.drop_column('drivers', 'alt_govt_id_type')
    op.drop_column('drivers', 'alt_govt_id_number')
    op.drop_column('drivers', 'badge_url')
    op.drop_column('drivers', 'badge_expiry_date')
    op.drop_column('drivers', 'badge_number')
    op.drop_column('drivers', 'license_url')
    op.drop_column('drivers', 'eye_verify_url')
    op.drop_column('drivers', 'eye_expiry_date')
    op.drop_column('drivers', 'eye_verify_status')
    op.drop_column('drivers', 'training_verify_url')
    op.drop_column('drivers', 'training_expiry_date')
    op.drop_column('drivers', 'training_verify_status')
    op.drop_column('drivers', 'medical_verify_url')
    op.drop_column('drivers', 'medical_expiry_date')
    op.drop_column('drivers', 'medical_verify_status')
    op.drop_column('drivers', 'police_verify_url')
    op.drop_column('drivers', 'police_expiry_date')
    op.drop_column('drivers', 'police_verify_status')
    op.drop_column('drivers', 'bg_verify_url')
    op.drop_column('drivers', 'bg_expiry_date')
    op.drop_column('drivers', 'bg_verify_status')
    op.drop_column('drivers', 'photo_url')
    op.drop_column('drivers', 'current_address')
    op.drop_column('drivers', 'permanent_address')
    op.drop_column('drivers', 'date_of_joining')
    op.drop_column('drivers', 'date_of_birth')
    op.drop_column('drivers', 'gender')
    op.drop_column('drivers', 'code')
    op.alter_column('drivers', 'license_expiry_date', new_column_name='license_expiry')
    op.create_unique_constraint('uq_driver_tenant_phone', 'drivers', ['tenant_id', 'phone'])
    op.create_unique_constraint('uq_driver_tenant_email', 'drivers', ['tenant_id', 'email'])

    # Revert vendors
    op.drop_constraint('uq_vendor_phone_per_tenant', 'vendors', type_='unique')
    op.drop_constraint('uq_vendor_email_per_tenant', 'vendors', type_='unique')
    op.drop_constraint('uq_vendor_code_per_tenant', 'vendors', type_='unique')
    op.drop_constraint('uq_vendor_name_per_tenant', 'vendors', type_='unique')
    op.drop_column('vendors', 'phone')
    op.drop_column('vendors', 'vendor_code')
    op.add_column('vendors', sa.Column('contact_person', sa.String(255), nullable=True))
    op.add_column('vendors', sa.Column('contact_number', sa.String(20), nullable=True))
    op.add_column('vendors', sa.Column('address', sa.Text(), nullable=True))
