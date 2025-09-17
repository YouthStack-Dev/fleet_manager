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
                "password": "hashed_password_123",  # replace with real hash in production
                "team_id": teams[0].team_id,
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
                "team_id": teams[-1].team_id,  # assign last team
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