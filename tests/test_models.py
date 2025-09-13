import pytest
from sqlalchemy.orm import Session
from datetime import date
from app.models import (
    Admin, Vendor, Driver, Vehicle, VehicleType, VendorUser, Team, 
    Tenant, Employee, Shift, Booking, Route, RouteBooking, WeekoffConfig
)
from tests.fixtures import *

def test_admin_model(db: Session, admin_data):
    # Create an admin
    admin = Admin(
        name=admin_data["name"],
        email=admin_data["email"],
        phone=admin_data["phone"],
        password=admin_data["password"],
        is_active=True
    )
    db.add(admin)
    db.commit()

    # Fetch the admin from the db
    fetched_admin = db.query(Admin).filter(Admin.email == admin_data["email"]).first()
    
    # Check that the admin was created correctly
    assert fetched_admin is not None
    assert fetched_admin.name == admin_data["name"]
    assert fetched_admin.email == admin_data["email"]
    assert fetched_admin.phone == admin_data["phone"]
    assert fetched_admin.is_active == True

def test_vendor_model(db: Session, vendor_data):
    # Create a vendor
    vendor = Vendor(**vendor_data)
    db.add(vendor)
    db.commit()

    # Fetch the vendor from the db
    fetched_vendor = db.query(Vendor).filter(Vendor.email == vendor_data["email"]).first()
    
    # Check that the vendor was created correctly
    assert fetched_vendor is not None
    assert fetched_vendor.name == vendor_data["name"]
    assert fetched_vendor.code == vendor_data["code"]
    assert fetched_vendor.email == vendor_data["email"]
    assert fetched_vendor.phone == vendor_data["phone"]
    assert fetched_vendor.is_active == True

def test_vendor_user_model(db: Session, create_vendor, vendor_user_data):
    # Create a vendor user
    vendor_user = VendorUser(
        name=vendor_user_data["name"],
        email=vendor_user_data["email"],
        phone=vendor_user_data["phone"],
        vendor_id=create_vendor.vendor_id,
        password=vendor_user_data["password"],
        is_active=True
    )
    db.add(vendor_user)
    db.commit()

    # Fetch the vendor user from the db
    fetched_vendor_user = db.query(VendorUser).filter(VendorUser.email == vendor_user_data["email"]).first()
    
    # Check that the vendor user was created correctly
    assert fetched_vendor_user is not None
    assert fetched_vendor_user.name == vendor_user_data["name"]
    assert fetched_vendor_user.email == vendor_user_data["email"]
    assert fetched_vendor_user.phone == vendor_user_data["phone"]
    assert fetched_vendor_user.vendor_id == create_vendor.vendor_id
    assert fetched_vendor_user.is_active == True

def test_driver_model(db: Session, create_vendor, driver_data):
    # Create a driver
    driver = Driver(
        name=driver_data["name"],
        code=driver_data["code"],
        email=driver_data["email"],
        phone=driver_data["phone"],
        vendor_id=create_vendor.vendor_id,
        password=driver_data["password"],
        license_number=driver_data["license_number"],
        is_active=True
    )
    db.add(driver)
    db.commit()

    # Fetch the driver from the db
    fetched_driver = db.query(Driver).filter(Driver.email == driver_data["email"]).first()
    
    # Check that the driver was created correctly
    assert fetched_driver is not None
    assert fetched_driver.name == driver_data["name"]
    assert fetched_driver.code == driver_data["code"]
    assert fetched_driver.email == driver_data["email"]
    assert fetched_driver.phone == driver_data["phone"]
    assert fetched_driver.vendor_id == create_vendor.vendor_id
    assert fetched_driver.license_number == driver_data["license_number"]
    assert fetched_driver.is_active == True

def test_employee_model(db: Session, create_team, employee_data):
    # Create an employee
    employee = Employee(
        name=employee_data["name"],
        email=employee_data["email"],
        phone=employee_data["phone"],
        employee_code=employee_data["employee_code"],
        team_id=create_team.team_id,
        password=employee_data["password"],
        is_active=True
    )
    db.add(employee)
    db.commit()

    # Fetch the employee from the db
    fetched_employee = db.query(Employee).filter(Employee.email == employee_data["email"]).first()
    
    # Check that the employee was created correctly
    assert fetched_employee is not None
    assert fetched_employee.name == employee_data["name"]
    assert fetched_employee.email == employee_data["email"]
    assert fetched_employee.phone == employee_data["phone"]
    assert fetched_employee.employee_code == employee_data["employee_code"]
    assert fetched_employee.team_id == create_team.team_id
    assert fetched_employee.is_active == True

def test_booking_model(db: Session, create_employee, create_shift, create_team, booking_data):
    # Create a booking
    booking = Booking(**booking_data)
    db.add(booking)
    db.commit()

    # Fetch the booking from the db
    fetched_booking = db.query(Booking).filter(
        Booking.employee_id == create_employee.employee_id,
        Booking.booking_date == booking_data["booking_date"]
    ).first()
    
    # Check that the booking was created correctly
    assert fetched_booking is not None
    assert fetched_booking.employee_id == create_employee.employee_id
    assert fetched_booking.shift_id == create_shift.shift_id
    assert fetched_booking.booking_date == booking_data["booking_date"]
    assert fetched_booking.pickup_location == booking_data["pickup_location"]
    assert fetched_booking.drop_location == booking_data["drop_location"]
    assert fetched_booking.status == booking_data["status"]
    assert fetched_booking.team_id == create_team.team_id
    assert fetched_booking.booking_type == booking_data["booking_type"]

def test_route_model(db: Session, create_shift, route_data):
    # Create a route
    route = Route(**route_data)
    db.add(route)
    db.commit()

    # Fetch the route from the db
    fetched_route = db.query(Route).filter(
        Route.route_code == route_data["route_code"]
    ).first()
    
    # Check that the route was created correctly
    assert fetched_route is not None
    assert fetched_route.shift_id == create_shift.shift_id
    assert fetched_route.route_code == route_data["route_code"]
    assert fetched_route.planned_distance_km == route_data["planned_distance_km"]
    assert fetched_route.planned_duration_minutes == route_data["planned_duration_minutes"]
    assert fetched_route.status == route_data["status"]
    assert fetched_route.route_date == route_data["route_date"]
    assert fetched_route.is_active == True

def test_route_booking_relationship(db: Session, create_route, create_booking, route_booking_data):
    # Create a route booking
    route_booking = RouteBooking(**route_booking_data)
    db.add(route_booking)
    db.commit()

    # Fetch the route booking and check relationships
    fetched_route_booking = db.query(RouteBooking).filter(
        RouteBooking.route_id == create_route.route_id,
        RouteBooking.booking_id == create_booking.booking_id
    ).first()
    
    assert fetched_route_booking is not None
    assert fetched_route_booking.route_id == create_route.route_id
    assert fetched_route_booking.booking_id == create_booking.booking_id
    assert fetched_route_booking.planned_eta_minutes == route_booking_data["planned_eta_minutes"]
    assert fetched_route_booking.sequence_number == route_booking_data["sequence_number"]
    
    # Test bidirectional relationships
    assert fetched_route_booking.route.route_id == create_route.route_id
    assert fetched_route_booking.booking.booking_id == create_booking.booking_id

def test_weekoff_config(db: Session, create_employee, weekoff_config_data):
    # Create a weekoff config
    weekoff_config = WeekoffConfig(**weekoff_config_data)
    db.add(weekoff_config)
    db.commit()

    # Fetch the weekoff config from db
    fetched_weekoff_config = db.query(WeekoffConfig).filter(
        WeekoffConfig.employee_id == create_employee.employee_id
    ).first()
    
    # Check that the weekoff config was created correctly
    assert fetched_weekoff_config is not None
    assert fetched_weekoff_config.employee_id == create_employee.employee_id
    assert fetched_weekoff_config.weekday == weekoff_config_data["weekday"]
    assert fetched_weekoff_config.is_weekoff == weekoff_config_data["is_weekoff"]
    
    # Test relationship to employee
    assert fetched_weekoff_config.employee.employee_id == create_employee.employee_id
