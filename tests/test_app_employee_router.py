"""
Comprehensive test suite for Employee Mobile App Router endpoints.

Tests cover:
1. GET /employee/bookings - Fetch employee bookings
2. PUT /employee/bookings/{booking_id} - Update employee booking

Each endpoint is tested for:
- Success scenarios
- Error cases (not found, invalid input, authorization)
- Edge cases (date ranges, cutoff times, duplicate bookings)
- Business logic validation
"""

import pytest
from datetime import date, datetime, time, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatusEnum, BookingTypeEnum
from app.models.shift import Shift, ShiftLogTypeEnum
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum
from app.models.employee import Employee, GenderEnum
from app.models.cutoff import Cutoff


# ==========================================
# Fixtures
# ==========================================

@pytest.fixture(scope="function")
def employee_shift_in(test_db, test_tenant):
    """Create a test shift for login"""
    shift = Shift(
        shift_id=1,
        tenant_id=test_tenant.tenant_id,
        shift_code="MORNING_IN",
        shift_time=time(9, 0, 0),
        log_type=ShiftLogTypeEnum.IN,
        is_active=True
    )
    test_db.add(shift)
    test_db.commit()
    test_db.refresh(shift)
    return shift


@pytest.fixture(scope="function")
def employee_shift_out(test_db, test_tenant):
    """Create a test shift for logout"""
    shift = Shift(
        shift_id=2,
        tenant_id=test_tenant.tenant_id,
        shift_code="EVENING_OUT",
        shift_time=time(18, 0, 0),
        log_type=ShiftLogTypeEnum.OUT,
        is_active=True
    )
    test_db.add(shift)
    test_db.commit()
    test_db.refresh(shift)
    return shift


@pytest.fixture(scope="function")
def test_employee_app(test_db, test_tenant, test_team):
    """Create a test employee for app testing"""
    employee = Employee(
        employee_id=200,
        tenant_id=test_tenant.tenant_id,
        team_id=test_team.team_id,
        role_id=3,
        employee_code="EMP200",
        name="App Test Employee",
        email="appemployee@test.com",
        password="hashedpassword123",
        phone="9999999999",
        gender=GenderEnum.MALE,
        is_active=True
    )
    test_db.add(employee)
    test_db.commit()
    test_db.refresh(employee)
    return employee


@pytest.fixture(scope="function")
def employee_token(client: TestClient, test_employee_app) -> str:
    """Generate employee auth token"""
    from common_utils.auth.utils import create_access_token
    token = create_access_token(
        user_id=str(test_employee_app.employee_id),
        tenant_id=test_employee_app.tenant_id,
        user_type="employee",
        custom_claims={
            "email": test_employee_app.email,
            "permissions": [
                "app-employee.read",
                "app-employee.write",
                "app-employee.update",
                "booking.read"
            ]
        }
    )
    return f"Bearer {token}"


@pytest.fixture(scope="function")
def test_employee_booking(test_db, test_tenant, employee_shift_in, test_employee_app):
    """Create a test booking for employee"""
    booking = Booking(
        booking_id=1,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee_app.employee_id,
        employee_code=test_employee_app.employee_code,
        shift_id=employee_shift_in.shift_id,
        team_id=test_employee_app.team_id,
        booking_date=date.today(),
        booking_type=BookingTypeEnum.REGULAR,
        status=BookingStatusEnum.REQUEST,
        pickup_latitude=12.9716,
        pickup_longitude=77.5946,
        pickup_location="Bangalore, KA",
        drop_latitude=12.9352,
        drop_longitude=77.6245,
        drop_location="Whitefield, Bangalore",
        boarding_otp="1234",
        deboarding_otp="5678"
    )
    test_db.add(booking)
    test_db.commit()
    test_db.refresh(booking)
    return booking


@pytest.fixture(scope="function")
def test_scheduled_booking(test_db, test_tenant, employee_shift_in, test_employee_app):
    """Create a scheduled booking (cannot be updated)"""
    booking = Booking(
        booking_id=2,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee_app.employee_id,
        employee_code=test_employee_app.employee_code,
        shift_id=employee_shift_in.shift_id,
        team_id=test_employee_app.team_id,
        booking_date=date.today() + timedelta(days=1),
        booking_type=BookingTypeEnum.REGULAR,
        status=BookingStatusEnum.SCHEDULED,
        pickup_latitude=12.9716,
        pickup_longitude=77.5946,
        pickup_location="Bangalore, KA",
        drop_latitude=12.9352,
        drop_longitude=77.6245,
        drop_location="Whitefield, Bangalore"
    )
    test_db.add(booking)
    test_db.commit()
    test_db.refresh(booking)
    return booking


@pytest.fixture(scope="function")
def test_cancelled_booking(test_db, test_tenant, employee_shift_in, test_employee_app):
    """Create a cancelled booking (can be re-booked)"""
    booking = Booking(
        booking_id=3,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee_app.employee_id,
        employee_code=test_employee_app.employee_code,
        shift_id=employee_shift_in.shift_id,
        team_id=test_employee_app.team_id,
        booking_date=date.today() + timedelta(days=2),
        booking_type=BookingTypeEnum.REGULAR,
        status=BookingStatusEnum.CANCELLED,
        pickup_latitude=12.9716,
        pickup_longitude=77.5946,
        pickup_location="Bangalore, KA",
        drop_latitude=12.9352,
        drop_longitude=77.6245,
        drop_location="Whitefield, Bangalore"
    )
    test_db.add(booking)
    test_db.commit()
    test_db.refresh(booking)
    return booking


@pytest.fixture(scope="function")
def test_cutoff(test_db, test_tenant):
    """Create cutoff configuration"""
    cutoff = Cutoff(
        tenant_id=test_tenant.tenant_id,
        booking_login_cutoff=timedelta(hours=2),
        booking_logout_cutoff=timedelta(hours=2),
        cancel_login_cutoff=timedelta(hours=1),
        cancel_logout_cutoff=timedelta(hours=1),
        allow_adhoc_booking=True,
        adhoc_booking_cutoff=timedelta(hours=1),
        allow_medical_emergency_booking=True,
        medical_emergency_booking_cutoff=timedelta(minutes=30)
    )
    test_db.add(cutoff)
    test_db.commit()
    test_db.refresh(cutoff)
    return cutoff


# ==========================================
# Test Cases for GET /employee/bookings
# ==========================================

class TestGetEmployeeBookings:
    """Test cases for fetching employee bookings"""

    def test_get_bookings_success(
        self, client: TestClient, employee_token: str, test_employee_booking
    ):
        """Successfully fetch employee bookings"""
        start = date.today()
        end = date.today() + timedelta(days=7)
        
        response = client.get(
            f"/api/v1/employee/bookings?start_date={start}&end_date={end}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Employee bookings fetched successfully"
        # API returns paginated response where data["data"] is the items list directly
        assert len(data["data"]) > 0
        
        booking = data["data"][0]
        assert booking["booking_id"] == test_employee_booking.booking_id
        assert booking["status"] == "Request"
        assert "shift_time" in booking
        assert "route_details" in booking

    def test_get_bookings_with_route_details(
        self, client: TestClient, employee_token: str, test_employee_booking,
        test_db, test_driver, test_vehicle
    ):
        """Fetch bookings with route details when assigned"""
        # Create route
        route = RouteManagement(
            tenant_id=test_employee_booking.tenant_id,
            route_code="EMP_ROUTE_1",
            shift_id=test_employee_booking.shift_id,
            assigned_driver_id=test_driver.driver_id,
            assigned_vehicle_id=test_vehicle.vehicle_id,
            status=RouteManagementStatusEnum.DRIVER_ASSIGNED
        )
        test_db.add(route)
        test_db.flush()
        
        # Link booking to route
        route_booking = RouteManagementBooking(
            route_id=route.route_id,
            booking_id=test_employee_booking.booking_id,
            order_id=1,
            estimated_pick_up_time="09:00",
            estimated_drop_time="09:30",
            estimated_distance=10.5
        )
        test_db.add(route_booking)
        test_db.commit()
        
        start = date.today()
        end = date.today() + timedelta(days=7)
        
        response = client.get(
            f"/api/v1/employee/bookings?start_date={start}&end_date={end}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        booking = data["data"][0]
        
        assert booking["route_details"] is not None
        assert "route_id" in booking["route_details"]
        assert "vehicle_details" in booking["route_details"]
        assert "driver_details" in booking["route_details"]

    def test_get_bookings_empty_result(
        self, client: TestClient, employee_token: str
    ):
        """Fetch bookings when none exist in date range"""
        start = date.today() + timedelta(days=100)
        end = date.today() + timedelta(days=107)
        
        response = client.get(
            f"/api/v1/employee/bookings?start_date={start}&end_date={end}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 0

    def test_get_bookings_invalid_date_range(
        self, client: TestClient, employee_token: str
    ):
        """Cannot fetch bookings with date range exceeding 31 days"""
        start = date.today()
        end = date.today() + timedelta(days=32)
        
        response = client.get(
            f"/api/v1/employee/bookings?start_date={start}&end_date={end}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "date range" in str(data).lower() or "31 days" in str(data).lower()

    def test_get_bookings_multiple_bookings(
        self, client: TestClient, employee_token: str, test_db, 
        test_tenant, employee_shift_in, test_employee_app
    ):
        """Fetch multiple bookings in date range"""
        # Create multiple bookings
        for i in range(3):
            booking = Booking(
                tenant_id=test_tenant.tenant_id,
                employee_id=test_employee_app.employee_id,
                employee_code=test_employee_app.employee_code,
                shift_id=employee_shift_in.shift_id,
                team_id=test_employee_app.team_id,
                booking_date=date.today() + timedelta(days=i),
                booking_type=BookingTypeEnum.REGULAR,
                status=BookingStatusEnum.REQUEST,
                pickup_latitude=12.9716,
                pickup_longitude=77.5946,
                pickup_location="Bangalore, KA",
                drop_latitude=12.9352,
                drop_longitude=77.6245,
                drop_location="Whitefield, Bangalore"
            )
            test_db.add(booking)
        test_db.commit()
        
        start = date.today()
        end = date.today() + timedelta(days=7)
        
        response = client.get(
            f"/api/v1/employee/bookings?start_date={start}&end_date={end}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 3

    def test_get_bookings_unauthorized(self, client: TestClient):
        """Cannot fetch bookings without authentication"""
        start = date.today()
        end = date.today() + timedelta(days=7)
        
        response = client.get(
            f"/api/v1/employee/bookings?start_date={start}&end_date={end}"
        )
        
        assert response.status_code == 401

    def test_get_bookings_missing_params(
        self, client: TestClient, employee_token: str
    ):
        """Cannot fetch bookings without required parameters"""
        response = client.get(
            "/api/v1/employee/bookings",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == 422  # Validation error


    def test_complete_employee_workflow(
        self, client: TestClient, employee_token: str, test_db,
        test_tenant, employee_shift_in, employee_shift_out, test_employee_app
    ):
        """
        Test complete employee workflow:
        1. Create booking
        2. Fetch bookings
        3. Update booking shift
        4. Cancel and re-book
        """
        # Step 1: Create initial booking
        booking = Booking(
            tenant_id=test_tenant.tenant_id,
            employee_id=test_employee_app.employee_id,
            employee_code=test_employee_app.employee_code,
            shift_id=employee_shift_in.shift_id,
            team_id=test_employee_app.team_id,
            booking_date=date.today() + timedelta(days=5),
            booking_type=BookingTypeEnum.REGULAR,
            status=BookingStatusEnum.REQUEST,
            pickup_latitude=12.9716,
            pickup_longitude=77.5946,
            pickup_location="Bangalore, KA",
            drop_latitude=12.9352,
            drop_longitude=77.6245,
            drop_location="Whitefield, Bangalore"
        )
        test_db.add(booking)
        test_db.commit()
        test_db.refresh(booking)
        
        # Step 2: Fetch bookings
        response = client.get(
            f"/api/v1/employee/bookings?start_date={date.today()}&end_date={date.today() + timedelta(days=7)}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) > 0
        
        # Step 3: Update shift
        response = client.put(
            f"/api/v1/bookings/{booking.booking_id}",
            json={"shift_id": employee_shift_out.shift_id},
            headers={"Authorization": employee_token}
        )
        assert response.status_code == 200
        assert response.json()["data"]["shift_id"] == employee_shift_out.shift_id
        
        # Step 4: Cancel booking (simulated by changing status)
        booking.status = BookingStatusEnum.CANCELLED
        test_db.commit()
        
        # Step 5: Re-book cancelled booking
        response = client.put(
            f"/api/v1/bookings/{booking.booking_id}",
            json={"shift_id": employee_shift_in.shift_id},
            headers={"Authorization": employee_token}
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "Request"
        assert response.json()["data"]["shift_id"] == employee_shift_in.shift_id
