"""
Test cases for Driver App Router endpoints.

Covers all 6 endpoints:
1. POST /driver/duty/start - Start driver duty
2. GET /driver/trips - Get driver trips (upcoming/ongoing/completed)
3. POST /driver/trip/start - Start pickup for booking
4. PUT /driver/trip/no-show - Mark booking as no-show
5. PUT /driver/trip/drop - Complete drop
6. PUT /driver/duty/end - End driver duty
"""
import pytest
from fastapi.testclient import TestClient
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from common_utils.auth.utils import create_access_token


@pytest.fixture(scope="function")
def driver_token(test_driver):
    """Generate JWT token for driver user"""
    token = create_access_token(
        user_id=str(test_driver.driver_id),
        tenant_id=test_driver.tenant_id,
        user_type="driver",
        custom_claims={
            "email": test_driver.email,
            "vendor_id": test_driver.vendor_id,
            "permissions": [
                "app-driver.read",
                "app-driver.write"
            ]
        }
    )
    return f"Bearer {token}"


@pytest.fixture(scope="function")
def test_shift(test_db, test_tenant):
    """Create a test shift"""
    from app.models.shift import Shift, ShiftLogTypeEnum
    from datetime import time
    shift = Shift(
        shift_id=1,
        tenant_id=test_tenant.tenant_id,
        shift_code="MORNING_SHIFT",
        shift_time=time(9, 0, 0),
        log_type=ShiftLogTypeEnum.IN,
        is_active=True
    )
    test_db.add(shift)
    test_db.commit()
    test_db.refresh(shift)
    return shift


@pytest.fixture(scope="function")
def test_employee_for_booking(test_db, test_tenant, test_team):
    """Create a test employee for booking"""
    from app.models.employee import Employee, GenderEnum
    employee = Employee(
        employee_id=100,
        tenant_id=test_tenant.tenant_id,
        team_id=test_team.team_id,
        role_id=3,
        employee_code="EMP100",
        name="Test Employee",
        email="employee100@test.com",
        password="hashedpassword123",
        phone="1111111111",
        gender=GenderEnum.MALE,
        is_active=True
    )
    test_db.add(employee)
    test_db.commit()
    test_db.refresh(employee)
    return employee


@pytest.fixture(scope="function")
def test_booking(test_db, test_tenant, test_shift, test_employee_for_booking):
    """Create a test booking"""
    from app.models.booking import Booking, BookingTypeEnum, BookingStatusEnum
    booking = Booking(
        booking_id=1,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee_for_booking.employee_id,
        employee_code=test_employee_for_booking.employee_code,
        shift_id=test_shift.shift_id,
        team_id=test_employee_for_booking.team_id,
        booking_date=date.today(),
        booking_type=BookingTypeEnum.REGULAR,
        status=BookingStatusEnum.SCHEDULED,
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
def test_route_assigned(test_db, test_tenant, test_shift, test_driver, test_vehicle, test_vendor):
    """Create a test route assigned to driver"""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum
    route = RouteManagement(
        route_id=1,
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift.shift_id,
        route_code="ROUTE001",
        status=RouteManagementStatusEnum.DRIVER_ASSIGNED,
        assigned_vendor_id=test_vendor.vendor_id,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_driver_id=test_driver.driver_id,
        escort_required=False,
        estimated_total_distance=10.5,
        estimated_total_time=30.0,
        buffer_time=5
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route


@pytest.fixture(scope="function")
def test_route_ongoing(test_db, test_tenant, test_shift, test_driver, test_vehicle, test_vendor):
    """Create a test route in ONGOING status"""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum
    route = RouteManagement(
        route_id=2,
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift.shift_id,
        route_code="ROUTE002",
        status=RouteManagementStatusEnum.ONGOING,
        assigned_vendor_id=test_vendor.vendor_id,
        assigned_vehicle_id=test_vehicle.vehicle_id,
        assigned_driver_id=test_driver.driver_id,
        escort_required=False,
        estimated_total_distance=10.5,
        estimated_total_time=30.0,
        buffer_time=5
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route


@pytest.fixture(scope="function")
def test_route_booking(test_db, test_route_assigned, test_booking):
    """Link booking to route"""
    from app.models.route_management import RouteManagementBooking
    route_booking = RouteManagementBooking(
        route_id=test_route_assigned.route_id,
        booking_id=test_booking.booking_id,
        order_id=1,
        estimated_pick_up_time="09:00",
        estimated_drop_time="09:30",
        estimated_distance=10.5
    )
    test_db.add(route_booking)
    test_db.commit()
    test_db.refresh(route_booking)
    return route_booking


@pytest.fixture(scope="function")
def test_route_booking_ongoing(test_db, test_route_ongoing, test_employee_for_booking):
    """Create booking for ongoing route"""
    from app.models.booking import Booking, BookingTypeEnum, BookingStatusEnum
    from app.models.route_management import RouteManagementBooking
    
    booking = Booking(
        booking_id=10,
        tenant_id=test_route_ongoing.tenant_id,
        employee_id=test_employee_for_booking.employee_id,
        employee_code=test_employee_for_booking.employee_code,
        shift_id=test_route_ongoing.shift_id,
        team_id=test_employee_for_booking.team_id,
        booking_date=date.today(),
        booking_type=BookingTypeEnum.REGULAR,
        status=BookingStatusEnum.SCHEDULED,
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
    test_db.flush()
    
    route_booking = RouteManagementBooking(
        route_id=test_route_ongoing.route_id,
        booking_id=booking.booking_id,
        order_id=1,
        estimated_pick_up_time="09:00",
        estimated_drop_time="09:30",
        estimated_distance=10.5
    )
    test_db.add(route_booking)
    test_db.commit()
    test_db.refresh(booking)
    test_db.refresh(route_booking)
    return {"booking": booking, "route_booking": route_booking}


# ==========================================
# Test Cases for POST /driver/duty/start
# ==========================================

class TestStartDuty:
    """Test cases for starting driver duty"""

    def test_start_duty_success(self, client: TestClient, driver_token: str, test_route_assigned, test_route_booking):
        """Successfully start duty for assigned route"""
        response = client.post(
            f"/api/v1/driver/duty/start?route_id={test_route_assigned.route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["route_id"] == test_route_assigned.route_id
        assert data["data"]["route_status"] == "Ongoing"

    def test_start_duty_already_started(self, client: TestClient, driver_token: str, test_route_ongoing):
        """Idempotent: Starting already ongoing route returns success"""
        response = client.post(
            f"/api/v1/driver/duty/start?route_id={test_route_ongoing.route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "already started" in data["message"].lower()

    def test_start_duty_route_not_found(self, client: TestClient, driver_token: str):
        """Cannot start duty for non-existent route"""
        response = client.post(
            "/api/v1/driver/duty/start?route_id=999",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 404
        data = response.json()
        # HTTPException detail contains the ResponseWrapper.error dict
        assert "error_code" in data.get("detail", {}) or "ROUTE_NOT_FOUND" in str(data)

    def test_start_duty_wrong_status(self, client: TestClient, driver_token: str, test_route_ongoing, test_db):
        """Cannot start duty for route not in DRIVER_ASSIGNED state"""
        from app.models.route_management import RouteManagementStatusEnum
        # Change route to COMPLETED
        test_route_ongoing.status = RouteManagementStatusEnum.COMPLETED
        test_db.commit()
        
        response = client.post(
            f"/api/v1/driver/duty/start?route_id={test_route_ongoing.route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400
        data = response.json()
        assert "INVALID_ROUTE_STATE" in str(data)

    def test_start_duty_already_has_ongoing_route(
        self, client: TestClient, driver_token: str, test_route_assigned, test_route_ongoing, test_db
    ):
        """Cannot start new duty when driver has ongoing route"""
        response = client.post(
            f"/api/v1/driver/duty/start?route_id={test_route_assigned.route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400
        data = response.json()
        assert "DRIVER_HAS_ONGOING_ROUTE" in str(data)

    def test_start_duty_unauthorized(self, client: TestClient, test_route_assigned):
        """Unauthorized access without token"""
        response = client.post(
            f"/api/v1/driver/duty/start?route_id={test_route_assigned.route_id}"
        )
        assert response.status_code == 401


# ==========================================
# Test Cases for GET /driver/trips
# ==========================================

class TestGetDriverTrips:
    """Test cases for fetching driver trips"""

    def test_get_upcoming_trips(self, client: TestClient, driver_token: str, test_route_assigned, test_route_booking):
        """Get upcoming trips for driver"""
        response = client.get(
            f"/api/v1/driver/trips?status_filter=upcoming&booking_date={date.today()}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] >= 0

    def test_get_ongoing_trips(self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing):
        """Get ongoing trips for driver"""
        response = client.get(
            f"/api/v1/driver/trips?status_filter=ongoing&booking_date={date.today()}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] >= 0

    def test_get_completed_trips(self, client: TestClient, driver_token: str):
        """Get completed trips for driver"""
        response = client.get(
            f"/api/v1/driver/trips?status_filter=completed&booking_date={date.today()}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] >= 0

    def test_get_trips_invalid_status(self, client: TestClient, driver_token: str):
        """Invalid status filter returns validation error"""
        response = client.get(
            "/api/v1/driver/trips?status_filter=invalid",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 422  # Validation error

    def test_get_trips_no_results(self, client: TestClient, driver_token: str):
        """Returns empty list when no trips found"""
        future_date = date.today() + timedelta(days=30)
        response = client.get(
            f"/api/v1/driver/trips?status_filter=upcoming&booking_date={future_date}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 0

    def test_get_trips_unauthorized(self, client: TestClient):
        """Unauthorized access without token"""
        response = client.get("/api/v1/driver/trips?status_filter=upcoming")
        assert response.status_code == 401


# ==========================================
# Test Cases for POST /driver/trip/start
# ==========================================

class TestStartTrip:
    """Test cases for starting a trip (pickup)"""

    def test_start_trip_success(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing
    ):
        """Successfully start trip with valid OTP and location"""
        booking = test_route_booking_ongoing["booking"]
        response = client.post(
            f"/api/v1/driver/trip/start?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp=1234"
            f"&current_latitude={booking.pickup_latitude}"
            f"&current_longitude={booking.pickup_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["current_booking_id"] == booking.booking_id
        assert data["data"]["current_status"] == "Ongoing"

    def test_start_trip_route_not_found(self, client: TestClient, driver_token: str):
        """Cannot start trip for non-existent route"""
        response = client.post(
            "/api/v1/driver/trip/start?route_id=999&booking_id=1&otp=1234"
            "&current_latitude=12.9716&current_longitude=77.5946",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 404

    def test_start_trip_route_not_ongoing(
        self, client: TestClient, driver_token: str, test_route_assigned, test_booking
    ):
        """Cannot start trip if route not in ONGOING state"""
        response = client.post(
            f"/api/v1/driver/trip/start?route_id={test_route_assigned.route_id}"
            f"&booking_id={test_booking.booking_id}"
            f"&otp=1234"
            f"&current_latitude={test_booking.pickup_latitude}"
            f"&current_longitude={test_booking.pickup_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400

    def test_start_trip_booking_not_in_route(
        self, client: TestClient, driver_token: str, test_route_ongoing
    ):
        """Cannot start trip for booking not in route"""
        response = client.post(
            f"/api/v1/driver/trip/start?route_id={test_route_ongoing.route_id}"
            "&booking_id=999&otp=1234"
            "&current_latitude=12.9716&current_longitude=77.5946",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 404

    def test_start_trip_wrong_otp(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing
    ):
        """Cannot start trip with wrong OTP"""
        booking = test_route_booking_ongoing["booking"]
        response = client.post(
            f"/api/v1/driver/trip/start?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp=9999"  # Wrong OTP
            f"&current_latitude={booking.pickup_latitude}"
            f"&current_longitude={booking.pickup_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400
        data = response.json()
        response_str = str(data).lower()
        assert "otp" in response_str or "invalid" in response_str

    def test_start_trip_location_too_far(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing
    ):
        """Cannot start trip when driver is too far from pickup location"""
        booking = test_route_booking_ongoing["booking"]
        # Use coordinates far away from pickup location
        response = client.post(
            f"/api/v1/driver/trip/start?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp=1234"
            f"&current_latitude=13.0827&current_longitude=80.2707",  # Chennai (far away)
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400
        data = response.json()
        assert "DRIVER_TOO_FAR_FROM_PICKUP" in str(data)

    def test_start_trip_unauthorized(self, client: TestClient):
        """Unauthorized access without token"""
        response = client.post(
            "/api/v1/driver/trip/start?route_id=1&booking_id=1&otp=1234"
            "&current_latitude=12.9716&current_longitude=77.5946"
        )
        assert response.status_code == 401


# ==========================================
# Test Cases for PUT /driver/trip/no-show
# ==========================================

class TestMarkNoShow:
    """Test cases for marking booking as no-show"""

    def test_mark_no_show_success(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing, test_db
    ):
        """Successfully mark booking as no-show"""
        booking = test_route_booking_ongoing["booking"]
        response = client.put(
            f"/api/v1/driver/trip/no-show?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&reason=Employee not present",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["booking_status"] == "No-Show"

    def test_mark_no_show_route_not_found(self, client: TestClient, driver_token: str):
        """Cannot mark no-show for non-existent route"""
        response = client.put(
            "/api/v1/driver/trip/no-show?route_id=999&booking_id=1",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 404

    def test_mark_no_show_booking_not_in_route(
        self, client: TestClient, driver_token: str, test_route_ongoing
    ):
        """Cannot mark no-show for booking not in route"""
        response = client.put(
            f"/api/v1/driver/trip/no-show?route_id={test_route_ongoing.route_id}&booking_id=999",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 404

    def test_mark_no_show_already_ongoing(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing, test_db
    ):
        """Cannot mark no-show for ongoing booking"""
        from app.models.booking import BookingStatusEnum
        booking = test_route_booking_ongoing["booking"]
        booking.status = BookingStatusEnum.ONGOING
        test_db.commit()
        
        response = client.put(
            f"/api/v1/driver/trip/no-show?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400

    def test_mark_no_show_unauthorized(self, client: TestClient):
        """Unauthorized access without token"""
        response = client.put("/api/v1/driver/trip/no-show?route_id=1&booking_id=1")
        assert response.status_code == 401


# ==========================================
# Test Cases for PUT /driver/trip/drop
# ==========================================

class TestVerifyDrop:
    """Test cases for verifying drop (completing booking)"""

    def test_verify_drop_success(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing, test_db
    ):
        """Successfully verify drop with valid OTP and location"""
        from app.models.booking import BookingStatusEnum
        booking = test_route_booking_ongoing["booking"]
        # First set booking to ONGOING
        booking.status = BookingStatusEnum.ONGOING
        test_db.commit()
        
        response = client.put(
            f"/api/v1/driver/trip/drop?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp=5678"
            f"&current_latitude={booking.drop_latitude}"
            f"&current_longitude={booking.drop_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["booking_status"] == "Completed"

    def test_verify_drop_route_not_ongoing(
        self, client: TestClient, driver_token: str, test_route_assigned, test_booking
    ):
        """Cannot verify drop if route not in ONGOING state"""
        response = client.put(
            f"/api/v1/driver/trip/drop?route_id={test_route_assigned.route_id}"
            f"&booking_id={test_booking.booking_id}"
            f"&otp=5678"
            f"&current_latitude={test_booking.drop_latitude}"
            f"&current_longitude={test_booking.drop_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 404

    def test_verify_drop_wrong_otp(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing, test_db
    ):
        """Cannot verify drop with wrong OTP"""
        from app.models.booking import BookingStatusEnum
        booking = test_route_booking_ongoing["booking"]
        booking.status = BookingStatusEnum.ONGOING
        test_db.commit()
        
        response = client.put(
            f"/api/v1/driver/trip/drop?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp=9999"  # Wrong OTP
            f"&current_latitude={booking.drop_latitude}"
            f"&current_longitude={booking.drop_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400
        data = response.json()
        assert "otp" in str(data).lower() or "invalid" in str(data).lower()

    def test_verify_drop_location_too_far(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing, test_db
    ):
        """Cannot verify drop when driver is too far from drop location"""
        from app.models.booking import BookingStatusEnum
        booking = test_route_booking_ongoing["booking"]
        booking.status = BookingStatusEnum.ONGOING
        test_db.commit()
        
        response = client.put(
            f"/api/v1/driver/trip/drop?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp=5678"
            f"&current_latitude=13.0827&current_longitude=80.2707",  # Far away
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400
        data = response.json()
        assert "DRIVER_TOO_FAR_FROM_DROP" in str(data)

    def test_verify_drop_already_completed(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing, test_db
    ):
        """Idempotent: Verifying already completed drop"""
        from app.models.booking import BookingStatusEnum
        booking = test_route_booking_ongoing["booking"]
        booking.status = BookingStatusEnum.COMPLETED
        test_db.commit()
        
        response = client.put(
            f"/api/v1/driver/trip/drop?route_id={test_route_ongoing.route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp=5678"
            f"&current_latitude={booking.drop_latitude}"
            f"&current_longitude={booking.drop_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200

    def test_verify_drop_unauthorized(self, client: TestClient):
        """Unauthorized access without token"""
        response = client.put(
            "/api/v1/driver/trip/drop?route_id=1&booking_id=1&otp=5678"
            "&current_latitude=12.9352&current_longitude=77.6245"
        )
        assert response.status_code == 401


# ==========================================
# Test Cases for PUT /driver/duty/end
# ==========================================

class TestEndDuty:
    """Test cases for ending driver duty"""

    def test_end_duty_success(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing, test_db
    ):
        """Successfully end duty when all bookings are finalized"""
        from app.models.booking import BookingStatusEnum
        # Mark all bookings as completed
        booking = test_route_booking_ongoing["booking"]
        booking.status = BookingStatusEnum.COMPLETED
        test_db.commit()
        
        response = client.put(
            f"/api/v1/driver/duty/end?route_id={test_route_ongoing.route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["route_status"] == "Completed"

    def test_end_duty_with_pending_bookings(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_route_booking_ongoing
    ):
        """Cannot end duty when bookings are still pending"""
        response = client.put(
            f"/api/v1/driver/duty/end?route_id={test_route_ongoing.route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400
        data = response.json()
        assert "PENDING_BOOKINGS_EXIST" in str(data)

    def test_end_duty_route_not_ongoing(
        self, client: TestClient, driver_token: str, test_route_assigned, test_db
    ):
        """Cannot end duty for route not in ONGOING state"""
        response = client.put(
            f"/api/v1/driver/duty/end?route_id={test_route_assigned.route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 400

    def test_end_duty_already_completed(
        self, client: TestClient, driver_token: str, test_route_ongoing, test_db
    ):
        """Idempotent: Ending already completed route"""
        from app.models.route_management import RouteManagementStatusEnum
        test_route_ongoing.status = RouteManagementStatusEnum.COMPLETED
        test_db.commit()
        
        response = client.put(
            f"/api/v1/driver/duty/end?route_id={test_route_ongoing.route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200

    def test_end_duty_route_not_found(self, client: TestClient, driver_token: str):
        """Cannot end duty for non-existent route"""
        response = client.put(
            "/api/v1/driver/duty/end?route_id=999",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 404

    def test_end_duty_unauthorized(self, client: TestClient):
        """Unauthorized access without token"""
        response = client.put("/api/v1/driver/duty/end?route_id=1")
        assert response.status_code == 401


# ==========================================
# Integration Test: Complete Driver Flow
# ==========================================

class TestCompleteDriverFlow:
    """Integration test covering complete driver workflow"""

    def test_complete_driver_journey(
        self, 
        client: TestClient, 
        driver_token: str, 
        test_route_assigned, 
        test_route_booking,
        test_booking,
        test_db
    ):
        """
        Test complete driver journey:
        1. Start duty
        2. Get trips
        3. Start trip (pickup)
        4. Verify drop
        5. End duty
        """
        route_id = test_route_assigned.route_id
        booking = test_booking
        
        # Step 1: Start duty
        response = client.post(
            f"/api/v1/driver/duty/start?route_id={route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        assert response.json()["data"]["route_status"] == "Ongoing"
        
        # Step 2: Get ongoing trips
        response = client.get(
            "/api/v1/driver/trips?status_filter=ongoing",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        
        # Step 3: Start trip (pickup)
        response = client.post(
            f"/api/v1/driver/trip/start?route_id={route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp={booking.boarding_otp}"
            f"&current_latitude={booking.pickup_latitude}"
            f"&current_longitude={booking.pickup_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        assert response.json()["data"]["current_status"] == "Ongoing"
        
        # Step 4: Verify drop
        response = client.put(
            f"/api/v1/driver/trip/drop?route_id={route_id}"
            f"&booking_id={booking.booking_id}"
            f"&otp={booking.deboarding_otp}"
            f"&current_latitude={booking.drop_latitude}"
            f"&current_longitude={booking.drop_longitude}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        assert response.json()["data"]["booking_status"] == "Completed"
        
        # Step 5: End duty
        response = client.put(
            f"/api/v1/driver/duty/end?route_id={route_id}",
            headers={"Authorization": driver_token}
        )
        assert response.status_code == 200
        assert response.json()["data"]["route_status"] == "Completed"
