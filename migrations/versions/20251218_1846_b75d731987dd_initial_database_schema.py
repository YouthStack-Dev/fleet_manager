"""initial database schema

Revision ID: b75d731987dd
Revises: 
Create Date: 2025-12-18 18:46:56.258329

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = 'b75d731987dd'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create all base tables required by the application
    # This migration creates the foundational schema that alert system depends on
    
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('latitude', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('longitude', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('tenant_id')
    )
    
    # Create permissions table
    op.create_table(
        'permissions',
        sa.Column('permission_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('resource', sa.String(length=100), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('permission_id'),
        sa.UniqueConstraint('resource', 'action', name='uq_permission_resource_action')
    )
    
    # Create roles table
    op.create_table(
        'roles',
        sa.Column('role_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=True),
        sa.Column('role_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_system_role', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('role_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE')
    )
    
    # Create policies table
    op.create_table(
        'policies',
        sa.Column('policy_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('policy_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE')
    )
    
    # Create role_policies association table
    op.create_table(
        'role_policies',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('policy_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('role_id', 'policy_id'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['policy_id'], ['policies.policy_id'], ondelete='CASCADE')
    )
    
    # Create policy_permissions association table
    op.create_table(
        'policy_permissions',
        sa.Column('policy_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('policy_id', 'permission_id'),
        sa.ForeignKeyConstraint(['policy_id'], ['policies.policy_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.permission_id'], ondelete='CASCADE')
    )
    
    # Create teams table
    op.create_table(
        'teams',
        sa.Column('team_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('team_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE')
    )
    
    # Create employees table
    op.create_table(
        'employees',
        sa.Column('employee_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('employee_code', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('alternate_phone', sa.String(length=20), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('gender', sa.String(length=20), nullable=True),
        sa.Column('special_needs', sa.String(length=255), nullable=True),
        sa.Column('special_needs_start_date', sa.Date(), nullable=True),
        sa.Column('special_needs_end_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('employee_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ondelete='SET NULL'),
        sa.UniqueConstraint('tenant_id', 'phone', name='uq_employee_tenant_phone'),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_employee_tenant_email')
    )
    
    # Create vendors table
    op.create_table(
        'vendors',
        sa.Column('vendor_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('contact_person', sa.String(length=255), nullable=True),
        sa.Column('contact_number', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('vendor_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE')
    )
    
    # Create drivers table
    op.create_table(
        'drivers',
        sa.Column('driver_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('license_number', sa.String(length=100), nullable=True),
        sa.Column('license_expiry', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('driver_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], ondelete='SET NULL'),
        sa.UniqueConstraint('tenant_id', 'phone', name='uq_driver_tenant_phone'),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_driver_tenant_email')
    )
    
    # Create vehicle_types table
    op.create_table(
        'vehicle_types',
        sa.Column('vehicle_type_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('seats', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('vehicle_type_id'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ondelete='CASCADE')
    )
    
    # Create vehicles table
    op.create_table(
        'vehicles',
        sa.Column('vehicle_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('vehicle_type_id', sa.Integer(), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('driver_id', sa.Integer(), nullable=True),
        sa.Column('rc_number', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('vehicle_id'),
        sa.ForeignKeyConstraint(['vehicle_type_id'], ['vehicle_types.vehicle_type_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['driver_id'], ['drivers.driver_id'], ondelete='SET NULL'),
        sa.UniqueConstraint('rc_number', name='uq_vehicle_rc_number')
    )
    
    # Create shifts table
    op.create_table(
        'shifts',
        sa.Column('shift_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('shift_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE')
    )
    
    # Create bookings table
    op.create_table(
        'bookings',
        sa.Column('booking_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('shift_id', sa.Integer(), nullable=True),
        sa.Column('booking_type', sa.String(length=20), nullable=False),
        sa.Column('booking_date', sa.Date(), nullable=False),
        sa.Column('pickup_latitude', sa.Float(), nullable=True),
        sa.Column('pickup_longitude', sa.Float(), nullable=True),
        sa.Column('drop_latitude', sa.Float(), nullable=True),
        sa.Column('drop_longitude', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('special_needs', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('booking_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.employee_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.shift_id'], ondelete='SET NULL')
    )
    op.create_index('ix_bookings_employee_id', 'bookings', ['employee_id'])
    op.create_index('ix_bookings_booking_date', 'bookings', ['booking_date'])
    op.create_index('ix_bookings_status', 'bookings', ['status'])
    
    # Create other supporting tables (escorts, cutoffs, weekoff_config, etc.)
    op.create_table(
        'escorts',
        sa.Column('escort_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('escort_id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ondelete='CASCADE')
    )
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_type', sa.String(length=50), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=True),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('changes', JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE')
    )
    op.create_index('ix_audit_logs_tenant_id', 'audit_logs', ['tenant_id'])
    op.create_index('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    

def downgrade() -> None:
    # Drop tables in reverse order to respect foreign key constraints
    op.drop_index('ix_audit_logs_timestamp', table_name='audit_logs')
    op.drop_index('ix_audit_logs_tenant_id', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('escorts')
    op.drop_index('ix_bookings_status', table_name='bookings')
    op.drop_index('ix_bookings_booking_date', table_name='bookings')
    op.drop_index('ix_bookings_employee_id', table_name='bookings')
    op.drop_table('bookings')
    op.drop_table('shifts')
    op.drop_table('vehicles')
    op.drop_table('vehicle_types')
    op.drop_table('drivers')
    op.drop_table('vendors')
    op.drop_table('employees')
    op.drop_table('teams')
    op.drop_table('policy_permissions')
    op.drop_table('role_policies')
    op.drop_table('policies')
    op.drop_table('roles')
    op.drop_table('permissions')
    op.drop_table('tenants')
