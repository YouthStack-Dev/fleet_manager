import logging
from sqlalchemy.orm import Session
from app.models import Admin, Role

logger = logging.getLogger(__name__)

def seed_admins(db: Session):
    """
    Seed admin users for existing roles (idempotent).
    """
    roles = db.query(Role).filter(Role.name.in_(["SuperAdmin", "Admin"])).all()
    if not roles:
        logger.warning("No roles found for admin seeding, skipping.")
        return

    for role in roles:
        # Check if admin with this role already exists
        existing = db.query(Admin).filter(Admin.role_id == role.role_id).first()
        if existing:
            logger.info(f"Admin for role {role.name} already exists, skipping.")
            continue

        admin_data = {
            "name": f"{role.name} User",
            "email": f"{role.name.lower()}@example.com",
            "phone": f"9000{role.role_id:05d}",
            "password": "hashed_password_123",  # replace with real hash
            "role_id": role.role_id,
            "is_active": True
        }

        admin = Admin(**admin_data)
        db.add(admin)
        logger.info(f"Admin '{admin.name}' created for role {role.name}.")

    db.commit()
    logger.info("✅ Admin seeding completed successfully.")

import logging
from sqlalchemy.orm import Session
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


def seed_tenants(db: Session):
    """
    Seed initial tenants (idempotent).
    """

    tenants_data = [
        {
            "name": "Sample Tenant",
            "tenant_code": "SAM001",
            "address": "123 MG Road, Bangalore",
            "longitude": 77.5946,
            "latitude": 12.9716,
        },
        {
            "name": "Test Tenant",
            "tenant_code": "TST001",
            "address": "456 Residency Road, Bangalore",
            "longitude": 77.6200,
            "latitude": 12.9500,
        },
    ]

    for data in tenants_data:
        existing = db.query(Tenant).filter(Tenant.tenant_code == data["tenant_code"]).first()
        if existing:
            logger.info(f"Tenant {data['tenant_code']} already exists, skipping.")
            continue

        tenant = Tenant(**data)
        db.add(tenant)
        logger.info(f"Tenant {data['tenant_code']} created.")

    db.commit()
    logger.info("Tenant seeding completed.")

from app.models.team import Team

from sqlalchemy.orm import Session
from app.models import Permission, Policy, Role
import logging

logger = logging.getLogger(__name__)

def seed_iam(db: Session):
    """
    Seed IAM: Permissions, Policies, and Roles (idempotent).
    """
    # --- Step 1: Permissions ---
    permission_matrix = {
        "users": ["create", "read", "update", "delete"],
        "employees": ["create", "read", "update", "delete"],
        "shifts": ["create", "read", "update", "delete"],
        "vendors": ["create", "read", "update", "delete"],
    }

    permissions_map = {}
    for module, actions in permission_matrix.items():
        for action in actions:
            existing = (
                db.query(Permission)
                .filter(Permission.module == module, Permission.action == action)
                .first()
            )
            if existing:
                logger.debug(f"Permission {module}:{action} already exists.")
                permissions_map[f"{module}:{action}"] = existing
                continue

            perm = Permission(
                module=module,
                action=action,
                description=f"{action.capitalize()} {module}",
            )
            db.add(perm)
            db.flush()  # assign ID
            permissions_map[f"{module}:{action}"] = perm
            logger.info(f"Permission {module}:{action} created.")

    # --- Step 2: Policies ---
    policies_def = {
        "UserManagementPolicy": ["users:create", "users:read", "users:update", "users:delete"],
        "EmployeeManagementPolicy": ["employees:create", "employees:read", "employees:update"],
        "ShiftManagementPolicy": ["shifts:create", "shifts:read", "shifts:update"],
        "VendorManagementPolicy": ["vendors:create", "vendors:read", "vendors:update"],
    }

    policies_map = {}
    for name, perms in policies_def.items():
        policy = db.query(Policy).filter(Policy.name == name).first()
        if not policy:
            policy = Policy(name=name, description=f"Policy for {name}")
            db.add(policy)
            logger.info(f"Policy {name} created.")
        else:
            logger.debug(f"Policy {name} already exists.")
        # attach permissions
        policy.permissions = [permissions_map[p] for p in perms if p in permissions_map]
        policies_map[name] = policy

    # --- Step 3: Roles ---
    roles_def = {
        "SuperAdmin": list(policies_map.keys()),  # all policies
        "Admin": ["UserManagementPolicy", "EmployeeManagementPolicy", "ShiftManagementPolicy"],
        "employee": ["EmployeeManagementPolicy", "ShiftManagementPolicy"],
    }

    for role_name, assigned_policies in roles_def.items():
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            role = Role(
                name=role_name,
                description=f"Role with {', '.join(assigned_policies)}",
                is_system_role=True,
            )
            db.add(role)
            logger.info(f"Role {role_name} created.")
        else:
            logger.debug(f"Role {role_name} already exists.")

        role.policies = [policies_map[p] for p in assigned_policies if p in policies_map]

    # Commit all
    db.commit()
    logger.info("✅ IAM seeding completed successfully.")


def seed_teams(db: Session):
    """
    Seed two teams per tenant (idempotent).
    """
    tenants = db.query(Tenant).all()
    if not tenants:
        logger.warning("No tenants found, skipping team seeding.")
        return

    for tenant in tenants:
        logger.info(f"Seeding teams for tenant {tenant.tenant_code} ({tenant.name})...")

        teams_data = [
            {
                "tenant_id": tenant.tenant_id,
                "name": f"{tenant.name} - Operations",
                "description": "Operations team handling daily tasks",
            },
            {
                "tenant_id": tenant.tenant_id,
                "name": f"{tenant.name} - Support",
                "description": "Support team assisting employees and customers",
            },
        ]

        for data in teams_data:
            existing = (
                db.query(Team)
                .filter(Team.tenant_id == data["tenant_id"], Team.name == data["name"])
                .first()
            )
            if existing:
                logger.info(f"Team '{data['name']}' already exists for tenant {tenant.tenant_code}, skipping.")
                continue

            team = Team(**data)
            db.add(team)
            logger.info(f"Team '{data['name']}' created for tenant {tenant.tenant_code}.")

    db.commit()
    logger.info("Team seeding completed.")

from app.models.employee import Employee, GenderEnum
import random

def seed_employees(db: Session):
    """
    Seed two employees per tenant (idempotent).
    """
    tenants = db.query(Tenant).all()
    if not tenants:
        logger.warning("No tenants found, skipping employee seeding.")
        return

    # Fetch roles dynamically
    roles_map = {role.name: role.role_id for role in db.query(Role).all()}

    superadmin_role_id = roles_map.get("SuperAdmin")
    admin_role_id = roles_map.get("Admin")

    if superadmin_role_id is None or admin_role_id is None:
        raise ValueError("Required roles 'SuperAdmin' or 'Admin' are missing. Run IAM seed first.")

    for tenant in tenants:
        teams = db.query(Team).filter(Team.tenant_id == tenant.tenant_id).all()
        if not teams:
            logger.warning(f"No teams found for tenant {tenant.tenant_code}, skipping employees.")
            continue

        logger.info(f"Seeding employees for tenant {tenant.tenant_code} ({tenant.name})...")

        employees_data = [
            {
                "tenant_id": tenant.tenant_id,
                "employee_code": f"{tenant.tenant_code}-EMP1",
                "name": f"{tenant.name} Employee One",
                "email": f"{tenant.tenant_code.lower()}_emp1@example.com",
                "password": "hashed_password_123",
                "team_id": teams[0].team_id,
                "role_id": superadmin_role_id,  # guaranteed to exist
                "phone": f"9000{random.randint(100000,999999)}",
                "gender": GenderEnum.MALE,
                "address": "123 Main Street, Bangalore",
            },
            {
                "tenant_id": tenant.tenant_id,
                "employee_code": f"{tenant.tenant_code}-EMP2",
                "name": f"{tenant.name} Employee Two",
                "email": f"{tenant.tenant_code.lower()}_emp2@example.com",
                "password": "hashed_password_123",
                "team_id": teams[-1].team_id,
                "role_id": admin_role_id,  # guaranteed to exist
                "phone": f"8000{random.randint(100000,999999)}",
                "gender": GenderEnum.FEMALE,
                "address": "456 Market Road, Bangalore",
            },
        ]

        for data in employees_data:
            existing = (
                db.query(Employee)
                .filter(Employee.tenant_id == data["tenant_id"], Employee.employee_code == data["employee_code"])
                .first()
            )
            if existing:
                logger.info(f"Employee {data['employee_code']} already exists for tenant {tenant.tenant_code}, skipping.")
                continue

            emp = Employee(**data)
            db.add(emp)
            logger.info(f"Employee {data['employee_code']} created for tenant {tenant.tenant_code}.")

    db.commit()
    logger.info("Employee seeding completed.")

from app.models.shift import Shift, ShiftLogTypeEnum, PickupTypeEnum, GenderEnum as ShiftGenderEnum
from datetime import time


def seed_shifts(db: Session):
    """
    Seed three shifts per tenant (idempotent).
    """
    tenants = db.query(Tenant).all()
    if not tenants:
        logger.warning("No tenants found, skipping shift seeding.")
        return

    for tenant in tenants:
        logger.info(f"Seeding shifts for tenant {tenant.tenant_code} ({tenant.name})...")

        shifts_data = [
            {
                "tenant_id": tenant.tenant_id,
                "shift_code": f"{tenant.tenant_code}-SHIFT1",
                "log_type": ShiftLogTypeEnum.IN,
                "shift_time": time(9, 0),  # 9:00 AM
                "pickup_type": PickupTypeEnum.PICKUP,
                "gender": ShiftGenderEnum.MALE,
                "waiting_time_minutes": 10,
            },
            {
                "tenant_id": tenant.tenant_id,
                "shift_code": f"{tenant.tenant_code}-SHIFT2",
                "log_type": ShiftLogTypeEnum.OUT,
                "shift_time": time(18, 0),  # 6:00 PM
                "pickup_type": PickupTypeEnum.NODAL,
                "gender": ShiftGenderEnum.FEMALE,
                "waiting_time_minutes": 15,
            },
            {
                "tenant_id": tenant.tenant_id,
                "shift_code": f"{tenant.tenant_code}-SHIFT3",
                "log_type": ShiftLogTypeEnum.IN,
                "shift_time": time(22, 0),  # 10:00 PM
                "pickup_type": PickupTypeEnum.PICKUP,
                "gender": ShiftGenderEnum.OTHER,
                "waiting_time_minutes": 20,
            },
        ]

        for data in shifts_data:
            existing = (
                db.query(Shift)
                .filter(Shift.tenant_id == data["tenant_id"], Shift.shift_code == data["shift_code"])
                .first()
            )
            if existing:
                logger.info(f"Shift '{data['shift_code']}' already exists for tenant {tenant.tenant_code}, skipping.")
                continue

            shift = Shift(**data)
            db.add(shift)
            logger.info(f"Shift '{data['shift_code']}' created for tenant {tenant.tenant_code}.")

    db.commit()
    logger.info("Shift seeding completed.")

from sqlalchemy.orm import Session
from app.models import WeekoffConfig
def seed_weekoffs(db: Session):
    """
    Seed weekoff configs for selected employees (idempotent).
    """
    employees = db.query(Employee).filter(Employee.employee_id.in_([1, 2, 3, 4])).all()
    if not employees:
        logger.warning("No employees found for weekoff seeding.")
        return

    weekoff_data = {
        1: {"sunday": True},                        # Emp 1 → Sunday off
        2: {"saturday": True},                      # Emp 2 → Saturday off
        3: {"saturday": True, "sunday": True},      # Emp 3 → Sat+Sun off
        4: {"wednesday": True},                     # Emp 4 → Mid-week off
    }

    for emp in employees:
        data = weekoff_data.get(emp.employee_id)
        if not data:
            continue

        existing = (
            db.query(WeekoffConfig)
            .filter(WeekoffConfig.employee_id == emp.employee_id)
            .first()
        )

        if existing:
            logger.info(f"Weekoff already exists for employee {emp.employee_id}, updating...")
            for key, value in data.items():
                setattr(existing, key, value)
        else:
            config = WeekoffConfig(employee_id=emp.employee_id, **data)
            db.add(config)
            logger.info(f"Weekoff created for employee {emp.employee_id}.")

    db.commit()
    logger.info("Weekoff seeding completed.")

from sqlalchemy.orm import Session
from app.models import Tenant, Vendor
import logging

logger = logging.getLogger(__name__)

def seed_vendors(db: Session):
    """
    Seed one default vendor (MLT) per tenant (idempotent).
    Vendor code stored as {tenant_code}-MLT.
    """
    tenants = db.query(Tenant).all()
    if not tenants:
        logger.warning("No tenants found, skipping vendor seeding.")
        return

    for tenant in tenants:
        vendor_code = f"{tenant.tenant_code}-MLT"
        existing = (
            db.query(Vendor)
            .filter(Vendor.tenant_id == tenant.tenant_id, Vendor.vendor_code == vendor_code)
            .first()
        )
        if existing:
            logger.info(f"Vendor '{vendor_code}' already exists for tenant {tenant.tenant_code}, skipping.")
            continue

        vendor = Vendor(
            tenant_id=tenant.tenant_id,
            vendor_code=vendor_code,
            name="MLT Logistics",
            email="mlt@vendor.com",
            phone=f"99999{tenant.tenant_id:05d}",
            is_active=True,
        )
        db.add(vendor)
        logger.info(f"Vendor '{vendor_code}' created for tenant {tenant.tenant_code}.")

    db.commit()
    logger.info("Vendor seeding completed.")

import logging
from sqlalchemy.orm import Session
from app.models import VendorUser, Vendor, Role, Tenant
import random

logger = logging.getLogger(__name__)

def seed_vendor_users(db: Session):
    """
    Seed VendorUsers (idempotent).
    Each tenant will have default VendorUsers for their vendors.
    """

    tenants = db.query(Tenant).all()
    if not tenants:
        logger.warning("No tenants found, skipping vendor user seeding.")
        return

    # Fetch roles dynamically
    roles_map = {role.name: role.role_id for role in db.query(Role).all()}

    superadmin_role_id = roles_map.get("SuperAdmin")
    admin_role_id = roles_map.get("Admin")

    if superadmin_role_id is None or admin_role_id is None:
        raise ValueError("Required roles 'SuperAdmin' or 'Admin' are missing. Run IAM seed first.")

    for tenant in tenants:
        vendors = db.query(Vendor).filter(Vendor.tenant_id == tenant.tenant_id).all()
        if not vendors:
            logger.warning(f"No vendors found for tenant {tenant.tenant_code}, skipping vendor user seeding.")
            continue

        for vendor in vendors:
            # Default users to seed for each vendor
            users_data = [
                {
                    "vendor_id": vendor.vendor_id,
                    "name": f"{vendor.name} Admin",
                    "email": f"{vendor.vendor_code.lower()}_admin@example.com",
                    "phone": f"9000{random.randint(100000,999999)}",
                    "password": "hashed_password_123",  # Replace with real hash in production
                    "role_id": admin_role_id,
                    "is_active": True
                },
                {
                    "vendor_id": vendor.vendor_id,
                    "name": f"{vendor.name} Dispatcher",
                    "email": f"{vendor.vendor_code.lower()}_dispatcher@example.com",
                    "phone": f"8000{random.randint(100000,999999)}",
                    "password": "hashed_password_123",
                    "role_id": superadmin_role_id,
                    "is_active": True
                }
            ]

            for data in users_data:
                # Check if user already exists for this vendor
                existing = db.query(VendorUser).filter(
                    VendorUser.vendor_id == data["vendor_id"],
                    VendorUser.email == data["email"]
                ).first()

                if existing:
                    logger.info(f"VendorUser {data['email']} already exists for vendor {vendor.vendor_code}, skipping.")
                    continue

                user = VendorUser(**data)
                db.add(user)
                logger.info(f"VendorUser {data['email']} created for vendor {vendor.vendor_code}.")

    db.commit()
    logger.info("✅ VendorUser seeding completed successfully.")

import logging
from sqlalchemy.orm import Session
from app.models import Driver, Vendor
from datetime import date
import random

logger = logging.getLogger(__name__)

def seed_drivers(db: Session):
    """
    Seed 2 drivers per vendor (idempotent).
    """
    vendors = db.query(Vendor).all()
    if not vendors:
        logger.warning("No vendors found, skipping driver seeding.")
        return

    for vendor in vendors:
        drivers_data = [
            {
                "vendor_id": vendor.vendor_id,
                "name": f"{vendor.name} Driver One",
                "code": f"{vendor.vendor_code}-DRV1",
                "email": f"{vendor.vendor_code.lower()}_drv1@example.com",
                "phone": f"9000{random.randint(100000,999999)}",
                "gender": "Male",
                "password": "hashed_password_123",  # replace with actual hash
                "date_of_birth": date(1990, 1, 1),
                "date_of_joining": date(2023, 1, 1),
                "permanent_address": "123 Main Street, Bangalore",
                "current_address": "123 Main Street, Bangalore",
                "license_number": f"{vendor.vendor_code}-LIC1",
                "badge_number": f"{vendor.vendor_code}-BADGE1",
                "alt_govt_id_number": f"{vendor.vendor_code}-GOV1",
                "bg_verify_status": "Pending",
                "police_verify_status": "Pending",
                "medical_verify_status": "Pending",
                "training_verify_status": "Pending",
                "eye_verify_status": "Pending",
                "induction_status": "Pending",
                "is_active": True,
            },
            {
                "vendor_id": vendor.vendor_id,
                "name": f"{vendor.name} Driver Two",
                "code": f"{vendor.vendor_code}-DRV2",
                "email": f"{vendor.vendor_code.lower()}_drv2@example.com",
                "phone": f"8000{random.randint(100000,999999)}",
                "gender": "Female",
                "password": "hashed_password_123",
                "date_of_birth": date(1992, 6, 15),
                "date_of_joining": date(2023, 6, 1),
                "permanent_address": "456 Market Road, Bangalore",
                "current_address": "456 Market Road, Bangalore",
                "license_number": f"{vendor.vendor_code}-LIC2",
                "badge_number": f"{vendor.vendor_code}-BADGE2",
                "alt_govt_id_number": f"{vendor.vendor_code}-GOV2",
                "bg_verify_status": "Pending",
                "police_verify_status": "Pending",
                "medical_verify_status": "Pending",
                "training_verify_status": "Pending",
                "eye_verify_status": "Pending",
                "induction_status": "Pending",
                "is_active": True,
            }
        ]

        for data in drivers_data:
            existing = db.query(Driver).filter(
                Driver.vendor_id == data["vendor_id"],
                Driver.email == data["email"]
            ).first()

            if existing:
                logger.info(f"Driver {data['email']} already exists for vendor {vendor.vendor_code}, skipping.")
                continue

            driver = Driver(**data)
            db.add(driver)
            logger.info(f"Driver {data['email']} created for vendor {vendor.vendor_code}.")

    db.commit()
    logger.info("✅ Driver seeding completed successfully.")

import logging
from sqlalchemy.orm import Session
from app.models import Vendor, VehicleType

logger = logging.getLogger(__name__)

def seed_vehicle_types(db: Session):
    """
    Seed 2 vehicle types per vendor (idempotent).
    """
    vendors = db.query(Vendor).all()
    if not vendors:
        logger.warning("No vendors found, skipping vehicle type seeding.")
        return

    for vendor in vendors:
        vehicle_types_data = [
            {
                "vendor_id": vendor.vendor_id,
                "name": f"{vendor.name} - Mini Van",
                "description": "Mini van suitable for small groups",
                "seats": 7,
                "is_active": True,
            },
            {
                "vendor_id": vendor.vendor_id,
                "name": f"{vendor.name} - Sedan",
                "description": "Sedan for 4 passengers",
                "seats": 4,
                "is_active": True,
            }
        ]

        for data in vehicle_types_data:
            existing = db.query(VehicleType).filter(
                VehicleType.vendor_id == data["vendor_id"],
                VehicleType.name == data["name"]
            ).first()

            if existing:
                logger.info(f"VehicleType '{data['name']}' already exists for vendor {vendor.vendor_code}, skipping.")
                continue

            vt = VehicleType(**data)
            db.add(vt)
            logger.info(f"VehicleType '{data['name']}' created for vendor {vendor.vendor_code}.")

    db.commit()
    logger.info("✅ VehicleType seeding completed successfully.")
import logging
from sqlalchemy.orm import Session
from app.models import Vendor, VehicleType, Driver, Vehicle

logger = logging.getLogger(__name__)

def seed_vehicles(db: Session):
    """
    Seed 2 vehicles per vendor (idempotent).
    Each vehicle is assigned a driver and a vehicle type.
    """
    vendors = db.query(Vendor).all()
    if not vendors:
        logger.warning("No vendors found, skipping vehicle seeding.")
        return

    for vendor in vendors:
        # Get vehicle types and drivers for this vendor
        vehicle_types = db.query(VehicleType).filter(VehicleType.vendor_id == vendor.vendor_id).all()
        drivers = db.query(Driver).filter(Driver.vendor_id == vendor.vendor_id).all()

        if not vehicle_types or not drivers:
            logger.warning(f"Vendor {vendor.vendor_code} has missing vehicle types or drivers, skipping vehicles.")
            continue

        vehicles_data = [
            {
                "vendor_id": vendor.vendor_id,
                "vehicle_type_id": vehicle_types[0].vehicle_type_id,
                "driver_id": drivers[0].driver_id,
                "rc_number": f"{vendor.vendor_code}-RC1",
                "description": f"{vendor.name} Mini Van Vehicle 1",
                "puc_number": f"{vendor.vendor_code}-PUC1",
                "fitness_number": f"{vendor.vendor_code}-FIT1",
                "tax_receipt_number": f"{vendor.vendor_code}-TAX1",
                "insurance_number": f"{vendor.vendor_code}-INS1",
                "permit_number": f"{vendor.vendor_code}-PER1",
                "is_active": True,
            },
            {
                "vendor_id": vendor.vendor_id,
                "vehicle_type_id": vehicle_types[-1].vehicle_type_id,
                "driver_id": drivers[-1].driver_id,
                "rc_number": f"{vendor.vendor_code}-RC2",
                "description": f"{vendor.name} Sedan Vehicle 2",
                "puc_number": f"{vendor.vendor_code}-PUC2",
                "fitness_number": f"{vendor.vendor_code}-FIT2",
                "tax_receipt_number": f"{vendor.vendor_code}-TAX2",
                "insurance_number": f"{vendor.vendor_code}-INS2",
                "permit_number": f"{vendor.vendor_code}-PER2",
                "is_active": True,
            }
        ]

        for data in vehicles_data:
            existing = db.query(Vehicle).filter(
                Vehicle.vendor_id == data["vendor_id"],
                Vehicle.rc_number == data["rc_number"]
            ).first()

            if existing:
                logger.info(f"Vehicle '{data['rc_number']}' already exists for vendor {vendor.vendor_code}, skipping.")
                continue

            vehicle = Vehicle(**data)
            db.add(vehicle)
            logger.info(f"Vehicle '{data['rc_number']}' created for vendor {vendor.vendor_code}.")

    db.commit()
    logger.info("✅ Vehicle seeding completed successfully.")
