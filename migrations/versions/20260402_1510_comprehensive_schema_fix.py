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
from sqlalchemy import inspect, text


revision = 'a3b4c5d6e7f8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def has_column(table, column):
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c['name'] for c in insp.get_columns(table)]


def has_table(table):
    bind = op.get_bind()
    insp = inspect(bind)
    return insp.has_table(table)


def has_constraint(table, constraint_name):
    bind = op.get_bind()
    insp = inspect(bind)
    constraints = (
        [c['name'] for c in insp.get_unique_constraints(table)] +
        [c['name'] for c in insp.get_check_constraints(table)]
    )
    return constraint_name in constraints


def upgrade():
    bind = op.get_bind()

    # ──────────────────────────────────────────────
    # 1. VENDORS TABLE
    # ──────────────────────────────────────────────
    # Drop old columns only if they exist
    if has_column('vendors', 'contact_person'):
        op.drop_column('vendors', 'contact_person')
    if has_column('vendors', 'contact_number'):
        op.drop_column('vendors', 'contact_number')
    if has_column('vendors', 'address'):
        op.drop_column('vendors', 'address')

    # Add new columns only if missing
    if not has_column('vendors', 'vendor_code'):
        op.add_column('vendors', sa.Column('vendor_code', sa.String(50), nullable=False, server_default='UNKNOWN'))
        op.alter_column('vendors', 'vendor_code', server_default=None)
    if not has_column('vendors', 'phone'):
        op.add_column('vendors', sa.Column('phone', sa.String(20), nullable=True))

    # Add unique constraints only if missing
    if not has_constraint('vendors', 'uq_vendor_name_per_tenant'):
        op.create_unique_constraint('uq_vendor_name_per_tenant', 'vendors', ['tenant_id', 'name'])
    if not has_constraint('vendors', 'uq_vendor_code_per_tenant'):
        op.create_unique_constraint('uq_vendor_code_per_tenant', 'vendors', ['tenant_id', 'vendor_code'])
    if not has_constraint('vendors', 'uq_vendor_email_per_tenant'):
        op.create_unique_constraint('uq_vendor_email_per_tenant', 'vendors', ['tenant_id', 'email'])
    if not has_constraint('vendors', 'uq_vendor_phone_per_tenant'):
        op.create_unique_constraint('uq_vendor_phone_per_tenant', 'vendors', ['tenant_id', 'phone'])

    # ──────────────────────────────────────────────
    # 2. DRIVERS TABLE
    # ──────────────────────────────────────────────
    # Rename license_expiry → license_expiry_date (only if old column still exists)
    if has_column('drivers', 'license_expiry') and not has_column('drivers', 'license_expiry_date'):
        op.alter_column('drivers', 'license_expiry', new_column_name='license_expiry_date')

    # Drop old unique constraints only if they exist
    for constraint in ['uq_driver_tenant_phone', 'uq_driver_tenant_email']:
        if has_constraint('drivers', constraint):
            op.drop_constraint(constraint, 'drivers', type_='unique')

    # Add missing columns
    for col_name, col_def in [
        ('code', sa.Column('code', sa.String(50), nullable=True)),
        ('gender', sa.Column('gender', sa.String(20), nullable=True)),
        ('date_of_birth', sa.Column('date_of_birth', sa.Date(), nullable=True)),
        ('date_of_joining', sa.Column('date_of_joining', sa.Date(), nullable=True)),
        ('permanent_address', sa.Column('permanent_address', sa.Text(), nullable=True)),
        ('current_address', sa.Column('current_address', sa.Text(), nullable=True)),
        ('photo_url', sa.Column('photo_url', sa.Text(), nullable=True)),
        ('bg_verify_status', sa.Column('bg_verify_status', sa.String(20), nullable=True)),
        ('bg_expiry_date', sa.Column('bg_expiry_date', sa.Date(), nullable=True)),
        ('bg_verify_url', sa.Column('bg_verify_url', sa.Text(), nullable=True)),
        ('police_verify_status', sa.Column('police_verify_status', sa.String(20), nullable=True)),
        ('police_expiry_date', sa.Column('police_expiry_date', sa.Date(), nullable=True)),
        ('police_verify_url', sa.Column('police_verify_url', sa.Text(), nullable=True)),
        ('medical_verify_status', sa.Column('medical_verify_status', sa.String(20), nullable=True)),
        ('medical_expiry_date', sa.Column('medical_expiry_date', sa.Date(), nullable=True)),
        ('medical_verify_url', sa.Column('medical_verify_url', sa.Text(), nullable=True)),
        ('training_verify_status', sa.Column('training_verify_status', sa.String(20), nullable=True)),
        ('training_expiry_date', sa.Column('training_expiry_date', sa.Date(), nullable=True)),
        ('training_verify_url', sa.Column('training_verify_url', sa.Text(), nullable=True)),
        ('eye_verify_status', sa.Column('eye_verify_status', sa.String(20), nullable=True)),
        ('eye_expiry_date', sa.Column('eye_expiry_date', sa.Date(), nullable=True)),
        ('eye_verify_url', sa.Column('eye_verify_url', sa.Text(), nullable=True)),
        ('license_url', sa.Column('license_url', sa.Text(), nullable=True)),
        ('badge_number', sa.Column('badge_number', sa.String(100), nullable=True)),
        ('badge_expiry_date', sa.Column('badge_expiry_date', sa.Date(), nullable=True)),
        ('badge_url', sa.Column('badge_url', sa.Text(), nullable=True)),
        ('alt_govt_id_number', sa.Column('alt_govt_id_number', sa.String(20), nullable=True)),
        ('alt_govt_id_type', sa.Column('alt_govt_id_type', sa.String(50), nullable=True)),
        ('alt_govt_id_url', sa.Column('alt_govt_id_url', sa.Text(), nullable=True)),
        ('induction_date', sa.Column('induction_date', sa.Date(), nullable=True)),
        ('induction_url', sa.Column('induction_url', sa.Text(), nullable=True)),
    ]:
        if not has_column('drivers', col_name):
            op.add_column('drivers', col_def)

    # Re-add unique constraints only if missing
    for constraint, cols in [
        ('uq_driver_tenant_email', ['tenant_id', 'email']),
        ('uq_driver_tenant_phone', ['tenant_id', 'phone']),
        ('uq_driver_code_per_vendor', ['vendor_id', 'code']),
        ('uq_driver_tenant_license', ['tenant_id', 'license_number']),
        ('uq_driver_tenant_badge', ['tenant_id', 'badge_number']),
        ('uq_driver_tenant_alt_govt_id', ['tenant_id', 'alt_govt_id_number']),
    ]:
        if not has_constraint('drivers', constraint):
            op.create_unique_constraint(constraint, 'drivers', cols)

    # ──────────────────────────────────────────────
    # 3. VEHICLES TABLE
    # ──────────────────────────────────────────────
    # Drop old global unique constraint only if it exists
    if has_constraint('vehicles', 'uq_vehicle_rc_number'):
        op.drop_constraint('uq_vehicle_rc_number', 'vehicles', type_='unique')

    # Add all missing document columns
    for col_name, col_def in [
        ('rc_expiry_date', sa.Column('rc_expiry_date', sa.Date(), nullable=True)),
        ('description', sa.Column('description', sa.Text(), nullable=True)),
        ('puc_number', sa.Column('puc_number', sa.String(100), nullable=True)),
        ('puc_expiry_date', sa.Column('puc_expiry_date', sa.Date(), nullable=True)),
        ('puc_url', sa.Column('puc_url', sa.Text(), nullable=True)),
        ('fitness_number', sa.Column('fitness_number', sa.String(100), nullable=True)),
        ('fitness_expiry_date', sa.Column('fitness_expiry_date', sa.Date(), nullable=True)),
        ('fitness_url', sa.Column('fitness_url', sa.Text(), nullable=True)),
        ('tax_receipt_number', sa.Column('tax_receipt_number', sa.String(100), nullable=True)),
        ('tax_receipt_date', sa.Column('tax_receipt_date', sa.Date(), nullable=True)),
        ('tax_receipt_url', sa.Column('tax_receipt_url', sa.Text(), nullable=True)),
        ('insurance_number', sa.Column('insurance_number', sa.String(100), nullable=True)),
        ('insurance_expiry_date', sa.Column('insurance_expiry_date', sa.Date(), nullable=True)),
        ('insurance_url', sa.Column('insurance_url', sa.Text(), nullable=True)),
        ('permit_number', sa.Column('permit_number', sa.String(100), nullable=True)),
        ('permit_expiry_date', sa.Column('permit_expiry_date', sa.Date(), nullable=True)),
        ('permit_url', sa.Column('permit_url', sa.Text(), nullable=True)),
    ]:
        if not has_column('vehicles', col_name):
            op.add_column('vehicles', col_def)

    # Add per-vendor unique constraints (matching model's __table_args__)
    for constraint, cols in [
        ('uq_vendor_rc_number', ['vendor_id', 'rc_number']),
        ('uq_vendor_puc_number', ['vendor_id', 'puc_number']),
        ('uq_vendor_fitness_number', ['vendor_id', 'fitness_number']),
        ('uq_vendor_tax_receipt_number', ['vendor_id', 'tax_receipt_number']),
        ('uq_vendor_insurance_number', ['vendor_id', 'insurance_number']),
        ('uq_vendor_permit_number', ['vendor_id', 'permit_number']),
    ]:
        if not has_constraint('vehicles', constraint):
            op.create_unique_constraint(constraint, 'vehicles', cols)

    # ──────────────────────────────────────────────
    # 4. VEHICLE_TYPES TABLE
    # ──────────────────────────────────────────────
    if not has_column('vehicle_types', 'description'):
        op.add_column('vehicle_types', sa.Column('description', sa.Text(), nullable=True))
    if not has_column('vehicle_types', 'is_active'):
        op.add_column('vehicle_types', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
        op.alter_column('vehicle_types', 'is_active', server_default=None)
    if not has_constraint('vehicle_types', 'uq_vendor_vehicle_type_name'):
        op.create_unique_constraint('uq_vendor_vehicle_type_name', 'vehicle_types', ['vendor_id', 'name'])

    # ──────────────────────────────────────────────
    # 5. EMPLOYEES TABLE - rename constraints
    # ──────────────────────────────────────────────
    if has_constraint('employees', 'uq_employee_tenant_phone'):
        op.drop_constraint('uq_employee_tenant_phone', 'employees', type_='unique')
    if has_constraint('employees', 'uq_employee_tenant_email'):
        op.drop_constraint('uq_employee_tenant_email', 'employees', type_='unique')
    if not has_constraint('employees', 'uq_employee_phone_per_tenant'):
        op.create_unique_constraint('uq_employee_phone_per_tenant', 'employees', ['tenant_id', 'phone'])
    if not has_constraint('employees', 'uq_employee_email_per_tenant'):
        op.create_unique_constraint('uq_employee_email_per_tenant', 'employees', ['tenant_id', 'email'])
    if not has_constraint('employees', 'uq_employee_code_per_tenant'):
        op.create_unique_constraint('uq_employee_code_per_tenant', 'employees', ['tenant_id', 'employee_code'])

    # ──────────────────────────────────────────────
    # 6. CREATE vendor_users TABLE (never existed in migrations)
    # ──────────────────────────────────────────────
    if not has_table('vendor_users'):
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
    if not has_table('weekoff_configs'):
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
    if not has_table('cutoffs'):
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
    if not has_table('tenant_configs'):
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
