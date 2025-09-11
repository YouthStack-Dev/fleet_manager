import pytest
from sqlalchemy.orm import Session
from datetime import datetime, date, time
from app.utils.auth import get_password_hash
from app.models import (
    Admin, Vendor, Driver, Vehicle, VehicleType, VendorUser, Team, 
    Tenant, Employee, Shift, Booking, Route, RouteBooking, WeekoffConfig
)

@pytest.fixture
def admin_data():
    return {
        "name": "Test Admin",
        "email": "admin@test.com",
        "phone": "9876543210",
        "password": "testpassword"
    }

@pytest.fixture
def create_admin(db: Session, admin_data):
    admin = Admin(
        name=admin_data["name"],
        email=admin_data["email"],
        phone=admin_data["phone"],
        password=get_password_hash(admin_data["password"]),
        is_active=True
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin

@pytest.fixture
def vendor_data():
    return {
        "name": "Test Vendor",
        "code": "TEST01",
        "email": "vendor@test.com",
        "phone": "9876543211",
        "is_active": True
    }

@pytest.fixture
def create_vendor(db: Session, vendor_data):
    vendor = Vendor(**vendor_data)
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor

@pytest.fixture
def vendor_user_data(create_vendor):
    return {
        "name": "Test Vendor User",
        "email": "vendoruser@test.com",
        "phone": "9876543212",
        "vendor_id": create_vendor.vendor_id,
        "password": "testpassword",
        "is_active": True
    }

@pytest.fixture
def create_vendor_user(db: Session, vendor_user_data):
    vendor_user = VendorUser(
        **{k: v for k, v in vendor_user_data.items() if k != 'password'},
        password=get_password_hash(vendor_user_data["password"])
    )
    db.add(vendor_user)
    db.commit()
    db.refresh(vendor_user)
    return vendor_user

@pytest.fixture
def team_data():
    return {
        "name": "Test Team",
        "description": "A team for testing"
    }

@pytest.fixture
def create_team(db: Session, team_data):
    team = Team(**team_data)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team

@pytest.fixture
def employee_data(create_team):
    return {
        "name": "Test Employee",
        "email": "employee@test.com",
        "phone": "9876543213",
        "employee_code": "EMP001",
        "team_id": create_team.team_id,
        "password": "testpassword",
        "is_active": True
    }

@pytest.fixture
def create_employee(db: Session, employee_data):
    employee = Employee(
        **{k: v for k, v in employee_data.items() if k != 'password'},
        password=get_password_hash(employee_data["password"])
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee

@pytest.fixture
def driver_data(create_vendor):
    return {
        "name": "Test Driver",
        "code": "DRV001",
        "email": "driver@test.com",
        "phone": "9876543214",
        "vendor_id": create_vendor.vendor_id,
        "password": "testpassword",
        "license_number": "DL12345",
        "is_active": True
    }

@pytest.fixture
def create_driver(db: Session, driver_data):
    driver = Driver(
        **{k: v for k, v in driver_data.items() if k != 'password'},
        password=get_password_hash(driver_data["password"])
    )
    db.add(driver)
    db.commit()
    db.refresh(driver)
    return driver

@pytest.fixture
def vehicle_type_data(create_vendor):
    return {
        "name": "Sedan",
        "vendor_id": create_vendor.vendor_id,
        "description": "A standard sedan car",
        "is_active": True
    }

@pytest.fixture
def create_vehicle_type(db: Session, vehicle_type_data):
    vehicle_type = VehicleType(**vehicle_type_data)
    db.add(vehicle_type)
    db.commit()
    db.refresh(vehicle_type)
    return vehicle_type

@pytest.fixture
def vehicle_data(create_vehicle_type, create_vendor, create_driver):
    return {
        "vehicle_type_id": create_vehicle_type.vehicle_type_id,
        "vendor_id": create_vendor.vendor_id,
        "driver_id": create_driver.driver_id,
        "rc_number": "DL01AB1234",
        "rc_expiry_date": date(2025, 12, 31),
        "description": "White Toyota Etios",
        "insurance_expiry_date": date(2024, 12, 31),
        "is_active": True
    }

@pytest.fixture
def create_vehicle(db: Session, vehicle_data):
    vehicle = Vehicle(**vehicle_data)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle

@pytest.fixture
def shift_data():
    return {
        "shift_code": "MORN_IN",
        "log_type": "IN",
        "shift_time": time(8, 0, 0),
        "pickup_type": "Pickup",
        "waiting_time_minutes": 15,
        "is_active": True
    }

@pytest.fixture
def create_shift(db: Session, shift_data):
    shift = Shift(**shift_data)
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift

@pytest.fixture
def booking_data(create_employee, create_shift, create_team):
    return {
        "employee_id": create_employee.employee_id,
        "shift_id": create_shift.shift_id,
        "booking_date": date.today(),
        "pickup_latitude": 28.6139,
        "pickup_longitude": 77.2090,
        "pickup_location": "Test Address",
        "drop_latitude": 28.7041,
        "drop_longitude": 77.1025,
        "drop_location": "Office",
        "status": "Pending",
        "team_id": create_team.team_id
    }

@pytest.fixture
def create_booking(db: Session, booking_data):
    booking = Booking(**booking_data)
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking

@pytest.fixture
def route_data(create_shift):
    return {
        "shift_id": create_shift.shift_id,
        "route_code": f"RT-TEST-{datetime.now().strftime('%Y%m%d')}",
        "status": "Planned",
        "planned_distance_km": 20.5,
        "planned_duration_minutes": 45,
        "is_active": True
    }

@pytest.fixture
def create_route(db: Session, route_data):
    route = Route(**route_data)
    db.add(route)
    db.commit()
    db.refresh(route)
    return route

@pytest.fixture
def route_booking_data(create_route, create_booking):
    return {
        "route_id": create_route.route_id,
        "booking_id": create_booking.booking_id,
        "planned_eta_minutes": 25
    }

@pytest.fixture
def create_route_booking(db: Session, route_booking_data):
    route_booking = RouteBooking(**route_booking_data)
    db.add(route_booking)
    db.commit()
    db.refresh(route_booking)
    return route_booking

@pytest.fixture
def weekoff_config_data(create_employee):
    return {
        "employee_id": create_employee.employee_id,
        "monday": False,
        "tuesday": False,
        "wednesday": False,
        "thursday": False,
        "friday": False,
        "saturday": True,
        "sunday": True
    }

@pytest.fixture
def create_weekoff_config(db: Session, weekoff_config_data):
    weekoff_config = WeekoffConfig(**weekoff_config_data)
    db.add(weekoff_config)
    db.commit()
    db.refresh(weekoff_config)
    return weekoff_config
