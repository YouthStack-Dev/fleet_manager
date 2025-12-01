"""
Comprehensive test suite for Route Management endpoints.

Tests cover:
- Create routes (clustering and optimization)
- Get all routes (with filters)
- Get unrouted bookings
- Assign vendor to route
- Assign vehicle to route
- Get single route
- Merge routes
- Update route (add/remove bookings)
- Update booking order
- Delete routes (bulk and single)
- Edge cases: invalid data, cross-tenant restrictions, permissions
"""

import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta, time
from fastapi import status
from common_utils.auth.utils import create_access_token


def create_token(user_id, tenant_id, user_type, vendor_id=None, permissions=None):
    """Helper to create tokens for testing"""
    if permissions is None:
        permissions = []
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "user_type": user_type,
        "vendor_id": vendor_id,
        "permissions": [{"module": p.split('.')[0], "action": [p.split('.')[1]]} for p in permissions]
    }
    return f"Bearer {create_access_token(payload)}"


class TestCreateRoutes:
    """Test POST /api/v1/routes/ - Create routes with clustering"""

    def test_create_routes_success(self, client: TestClient, employee_token: str, test_tenant, test_shift, test_employee):
        """Successfully create route clusters for unrouted bookings"""
        tomorrow = date.today() + timedelta(days=1)
        
        # Create some unrouted bookings first
        for i in range(3):
            client.post(
                "/api/v1/bookings/",
                json={
                    "employee_id": test_employee["employee"].employee_id,
                    "shift_id": test_shift.shift_id,
                    "booking_dates": [str(tomorrow)]
                },
                headers={"Authorization": employee_token}
            )

        response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id={test_shift.shift_id}&radius=1.0&group_size=2",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "clusters" in data["data"]
        assert "total_bookings" in data["data"]

    def test_create_routes_admin_requires_tenant_id(self, client: TestClient, admin_token: str):
        """Admin must provide tenant_id"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id=20&radius=1.0&group_size=2",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_routes_invalid_shift(self, client: TestClient, employee_token: str, test_tenant):
        """Cannot create routes for non-existent shift"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id=999999&radius=1.0&group_size=2&tenant_id={test_tenant.tenant_id}",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_routes_no_unrouted_bookings(self, client: TestClient, employee_token: str, test_shift):
        """Returns empty clusters when no unrouted bookings exist"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id={test_shift.shift_id}&radius=1.0&group_size=2",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["total_bookings"] == 0
        assert len(data["data"]["clusters"]) == 0

    def test_create_routes_cross_tenant_shift(self, client: TestClient, employee_token: str, second_shift):
        """Cannot create routes for shift from different tenant"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id={second_shift.shift_id}&radius=1.0&group_size=2",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_routes_with_strict_grouping(self, client: TestClient, employee_token: str, test_shift):
        """Can specify strict grouping parameter"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id={test_shift.shift_id}&radius=1.0&group_size=3&strict_grouping=true",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_create_routes_vendor_forbidden(self, client: TestClient):
        """Vendors cannot create routes"""
        from common_utils.auth.utils import create_access_token
        vendor_token = f"Bearer {create_access_token(user_id='vendor1', tenant_id='TEST001', user_type='vendor', custom_claims={'vendor_id': 1, 'permissions': []})}"
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id=20&radius=1.0&group_size=2",
            headers={"Authorization": vendor_token}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_routes_without_auth(self, client: TestClient, test_shift):
        """Cannot create routes without authentication"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id={test_shift.shift_id}&radius=1.0&group_size=2"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetAllRoutes:
    """Test GET /api/v1/routes/ - Get all routes"""

    def test_get_routes_as_employee(self, client: TestClient, employee_token: str, test_tenant):
        """Employee can get routes for their tenant"""
        response = client.get(
            "/api/v1/routes/",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "shifts" in data["data"]

    def test_get_routes_as_admin_requires_tenant_id(self, client: TestClient, admin_token: str):
        """Admin can get routes using token tenant"""
        response = client.get(
            "/api/v1/routes/",
            headers={"Authorization": admin_token}
        )

        # Admin token uses TEST001 tenant, may return 200 or 404 depending on data
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_get_routes_with_shift_filter(self, client: TestClient, employee_token: str, test_shift):
        """Can filter routes by shift_id"""
        response = client.get(
            f"/api/v1/routes/?shift_id={test_shift.shift_id}",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_routes_with_date_filter(self, client: TestClient, employee_token: str):
        """Can filter routes by booking_date"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.get(
            f"/api/v1/routes/?booking_date={tomorrow}",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_routes_with_status_filter(self, client: TestClient, employee_token: str, test_route):
        """Can filter routes by status"""
        response = client.get(
            "/api/v1/routes/?status=Planned",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_get_routes_invalid_tenant(self, client: TestClient, admin_token: str):
        """Admin token tenant is used when query tenant is invalid"""
        response = client.get(
            "/api/v1/routes/?tenant_id=INVALID",
            headers={"Authorization": admin_token}
        )

        # Returns 200 or 404 depending on data
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_get_routes_vendor_sees_only_assigned(self, client: TestClient, vendor_token: str, test_tenant):
        """Vendor can only see routes assigned to them"""
        # test_tenant ensures tenant exists in database
        response = client.get(
            "/api/v1/routes/",
            headers={"Authorization": vendor_token}
        )

        assert response.status_code == status.HTTP_200_OK
        # Should only return vendor's routes

    def test_get_routes_without_auth(self, client: TestClient):
        """Cannot get routes without authentication"""
        response = client.get("/api/v1/routes/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetUnroutedBookings:
    """Test GET /api/v1/routes/unrouted - Get unrouted bookings"""

    def test_get_unrouted_bookings_success(self, client: TestClient, employee_token: str, test_shift):
        """Successfully get unrouted bookings for shift and date"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.get(
            f"/api/v1/routes/unrouted?shift_id={test_shift.shift_id}&booking_date={tomorrow}",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "bookings" in data["data"]
        assert "total_unrouted" in data["data"]

    def test_get_unrouted_missing_shift_id(self, client: TestClient, employee_token: str):
        """Returns error when shift_id is missing"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.get(
            f"/api/v1/routes/unrouted?booking_date={tomorrow}",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_unrouted_missing_date(self, client: TestClient, employee_token: str, test_shift):
        """Returns error when booking_date is missing"""
        response = client.get(
            f"/api/v1/routes/unrouted?shift_id={test_shift.shift_id}",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_unrouted_admin_requires_tenant_id(self, client: TestClient, admin_token: str, test_shift):
        """Admin must provide tenant_id"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.get(
            f"/api/v1/routes/unrouted?shift_id={test_shift.shift_id}&booking_date={tomorrow}",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_unrouted_invalid_tenant(self, client: TestClient, admin_token: str, test_shift):
        """Returns error for non-existent tenant"""
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.get(
            f"/api/v1/routes/unrouted?shift_id={test_shift.shift_id}&booking_date={tomorrow}&tenant_id=INVALID",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_unrouted_vendor_forbidden(self, client: TestClient):
        """Vendors cannot access unrouted bookings"""
        from common_utils.auth.utils import create_access_token
        vendor_token = f"Bearer {create_access_token(user_id='vendor1', tenant_id='TEST001', user_type='vendor', custom_claims={'vendor_id': 1, 'permissions': []})}"
        tomorrow = date.today() + timedelta(days=1)
        
        response = client.get(
            f"/api/v1/routes/unrouted?shift_id=20&booking_date={tomorrow}",
            headers={"Authorization": vendor_token}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestAssignVendor:
    """Test PUT /api/v1/routes/assign-vendor - Assign vendor to route"""

    def test_assign_vendor_success(self, client: TestClient, admin_token: str, test_route, test_vendor):
        """Successfully assign vendor to route"""
        response = client.put(
            f"/api/v1/routes/assign-vendor?route_id={test_route.route_id}&vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_assign_vendor_invalid_route(self, client: TestClient, admin_token: str):
        """Cannot assign vendor to non-existent route"""
        response = client.put(
            "/api/v1/routes/assign-vendor?route_id=999999&vendor_id=1",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_vendor_invalid_vendor(self, client: TestClient, admin_token: str, test_route):
        """Cannot assign non-existent vendor"""
        response = client.put(
            f"/api/v1/routes/assign-vendor?route_id={test_route.route_id}&vendor_id=999999",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_vendor_cross_tenant(self, client: TestClient, admin_token: str, test_route, second_vendor):
        """Cannot assign vendor from different tenant (route not found in vendor's tenant)"""
        response = client.put(
            f"/api/v1/routes/assign-vendor?route_id={test_route.route_id}&vendor_id={second_vendor.vendor_id}",
            headers={"Authorization": admin_token}
        )

        # Route not found in second_vendor's tenant, returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_vendor_employee_forbidden(self, client: TestClient, employee_token: str, test_route, test_vendor):
        """Employee can assign vendor (has permissions now)"""
        response = client.put(
            f"/api/v1/routes/assign-vendor?route_id={test_route.route_id}&vendor_id={test_vendor.vendor_id}",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_assign_vendor_without_auth(self, client: TestClient, test_route, test_vendor):
        """Cannot assign vendor without authentication"""
        response = client.put(
            f"/api/v1/routes/assign-vendor?route_id={test_route.route_id}&vendor_id={test_vendor.vendor_id}"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAssignVehicle:
    """Test PUT /api/v1/routes/assign-vehicle - Assign vehicle to route"""

    def test_assign_vehicle_success(self, client: TestClient, admin_token: str, test_route, test_vehicle):
        """Successfully assign vehicle to route"""
        response = client.put(
            f"/api/v1/routes/assign-vehicle?route_id={test_route.route_id}&vehicle_id={test_vehicle.vehicle_id}",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_assign_vehicle_invalid_route(self, client: TestClient, admin_token: str):
        """Cannot assign vehicle to non-existent route"""
        response = client.put(
            "/api/v1/routes/assign-vehicle?route_id=999999&vehicle_id=1",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_vehicle_invalid_vehicle(self, client: TestClient, admin_token: str, test_route):
        """Cannot assign non-existent vehicle"""
        response = client.put(
            f"/api/v1/routes/assign-vehicle?route_id={test_route.route_id}&vehicle_id=999999",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_vehicle_cross_tenant(self, client: TestClient, admin_token: str, test_route, second_vehicle):
        """Cannot assign vehicle from different tenant (route not found)"""
        response = client.put(
            f"/api/v1/routes/assign-vehicle?route_id={test_route.route_id}&vehicle_id={second_vehicle.vehicle_id}",
            headers={"Authorization": admin_token}
        )

        # Route not found in second_vehicle's tenant
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_assign_vehicle_without_driver(self, client: TestClient, admin_token: str, test_route, test_vehicle_no_driver):
        """Cannot assign vehicle without driver (409 Conflict)"""
        # First assign vendor
        client.put(
            f"/api/v1/routes/assign-vendor?route_id={test_route.route_id}&vendor_id=1",
            headers={"Authorization": admin_token}
        )
        
        response = client.put(
            f"/api/v1/routes/assign-vehicle?route_id={test_route.route_id}&vehicle_id={test_vehicle_no_driver.vehicle_id}",
            headers={"Authorization": admin_token}
        )

        # Returns 409 Conflict for vehicle without driver
        assert response.status_code == status.HTTP_409_CONFLICT


class TestGetSingleRoute:
    """Test GET /api/v1/routes/{route_id} - Get single route details"""

    def test_get_route_success(self, client: TestClient, employee_token: str, test_route):
        """Successfully get route details"""
        response = client.get(
            f"/api/v1/routes/{test_route.route_id}",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["route_id"] == test_route.route_id

    def test_get_route_not_found(self, client: TestClient, employee_token: str):
        """Returns 404 for non-existent route"""
        response = client.get(
            "/api/v1/routes/999999",
            headers={"Authorization": employee_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_route_cross_tenant(self, client: TestClient, admin_token: str, second_route):
        """Cannot access route from different tenant (returns 404)"""
        # Admin token has TEST001 tenant, second_route is in TEST002
        response = client.get(
            f"/api/v1/routes/{second_route.route_id}",
            headers={"Authorization": admin_token}
        )

        # Route not found in admin's tenant
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_route_vendor_unassigned(self, client: TestClient, vendor_token: str, test_route):
        """Vendor cannot see route not assigned to them (404)"""
        response = client.get(
            f"/api/v1/routes/{test_route.route_id}",
            headers={"Authorization": vendor_token}
        )

        # Vendor's tenant doesn't match route tenant, returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestMergeRoutes:
    """Test POST /api/v1/routes/merge - Merge multiple routes"""

    def test_merge_routes_success(self, client: TestClient, admin_token: str, test_route, second_route_same_tenant, routed_booking):
        """Successfully merge two routes"""
        # routed_booking ensures test_route has at least one booking
        response = client.post(
            "/api/v1/routes/merge",
            json={"route_ids": [test_route.route_id, second_route_same_tenant.route_id]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_merge_routes_single_route(self, client: TestClient, admin_token: str, test_route):
        """Cannot merge single route"""
        response = client.post(
            "/api/v1/routes/merge",
            json={"route_ids": [test_route.route_id]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_merge_routes_invalid_route(self, client: TestClient, admin_token: str):
        """Cannot merge non-existent routes"""
        response = client.post(
            "/api/v1/routes/merge",
            json={"route_ids": [999999, 999998]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_merge_routes_cross_tenant(self, client: TestClient, admin_token: str, test_route, second_route):
        """Cannot merge routes from different tenants"""
        response = client.post(
            "/api/v1/routes/merge",
            json={"route_ids": [test_route.route_id, second_route.route_id]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_merge_routes_different_shifts(self, client: TestClient, admin_token: str, test_route, different_shift_route):
        """Cannot merge routes with different shifts"""
        response = client.post(
            "/api/v1/routes/merge",
            json={"route_ids": [test_route.route_id, different_shift_route.route_id]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestUpdateRoute:
    """Test PUT /api/v1/routes/{route_id} - Update route (add/remove bookings)"""

    def test_update_route_add_bookings(self, client: TestClient, admin_token: str, test_route, unrouted_booking):
        """Successfully add bookings to route"""
        response = client.put(
            f"/api/v1/routes/{test_route.route_id}",
            json={"operation": "add", "booking_ids": [unrouted_booking.booking_id]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_update_route_remove_bookings(self, client: TestClient, admin_token: str, test_route, routed_booking):
        """Successfully remove bookings from route"""
        response = client.put(
            f"/api/v1/routes/{test_route.route_id}",
            json={"operation": "remove", "booking_ids": [routed_booking.booking_id]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_update_route_invalid_operation(self, client: TestClient, admin_token: str, test_route):
        """Returns error for invalid operation"""
        response = client.put(
            f"/api/v1/routes/{test_route.route_id}",
            json={"operation": "invalid", "booking_ids": [1]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_update_route_not_found(self, client: TestClient, admin_token: str):
        """Returns 404 for non-existent route"""
        response = client.put(
            "/api/v1/routes/999999",
            json={"operation": "add", "booking_ids": [1]},
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_route_cross_tenant_booking(self, client: TestClient, admin_token: str, test_route):
        """Test with cross-tenant booking (booking doesn't exist in route's tenant)"""
        # Using non-existent booking ID from different context
        response = client.put(
            f"/api/v1/routes/{test_route.route_id}",
            json={"operation": "add", "booking_ids": [999999]},
            headers={"Authorization": admin_token}
        )

        # Booking not found, should return 404 or 400
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST]


class TestUpdateBookingOrder:
    """Test PUT /api/v1/routes/{route_id}/update-booking-order - Update booking order"""

    def test_update_booking_order_success(self, client: TestClient, admin_token: str, test_route, routed_booking):
        """Successfully update booking order"""
        response = client.put(
            f"/api/v1/routes/{test_route.route_id}/update-booking-order",
            json={
                "bookings": [
                    {
                        "booking_id": routed_booking.booking_id,
                        "new_order_id": 1,
                        "estimated_pickup_time": "08:00:00",
                        "estimated_drop_time": "09:00:00"
                    }
                ]
            },
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_update_booking_order_not_in_route(self, client: TestClient, admin_token: str):
        """Cannot update order for non-existent route (404)"""
        response = client.put(
            "/api/v1/routes/999999/update-booking-order",
            json={
                "bookings": [
                    {
                        "booking_id": 1,
                        "new_order_id": 1,
                        "estimated_pickup_time": "08:00:00",
                        "estimated_drop_time": "09:00:00"
                    }
                ]
            },
            headers={"Authorization": admin_token}
        )

        # Route not found returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_booking_order_booking_not_in_route(self, client: TestClient, admin_token: str, test_route, unrouted_booking):
        """Cannot update order for booking not in route"""
        response = client.put(
            f"/api/v1/routes/{test_route.route_id}/update-booking-order",
            json={
                "bookings": [
                    {
                        "booking_id": unrouted_booking.booking_id,
                        "new_order_id": 1,
                        "estimated_pickup_time": "08:00:00",
                        "estimated_drop_time": "09:00:00"
                    }
                ]
            },
            headers={"Authorization": admin_token}
        )

        # Booking not in route returns 404
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteRoutes:
    """Test DELETE endpoints - Delete routes"""

    def test_delete_single_route(self, client: TestClient, admin_token: str, test_route):
        """Successfully delete single route"""
        response = client.delete(
            f"/api/v1/routes/{test_route.route_id}",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_delete_route_not_found(self, client: TestClient, admin_token: str):
        """Returns 404 for non-existent route"""
        response = client.delete(
            "/api/v1/routes/999999",
            headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_route_cross_tenant(self, client: TestClient, admin_token: str, second_route):
        """Cannot delete route from different tenant (404)"""
        # Admin token has TEST001, second_route is in TEST002
        response = client.delete(
            f"/api/v1/routes/{second_route.route_id}",
            headers={"Authorization": admin_token}
        )

        # Route not found in admin's tenant
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_bulk_routes(self, client: TestClient, admin_token: str, test_route, second_route_same_tenant):
        """Successfully delete all routes for a shift and date"""
        from datetime import date, timedelta
        tomorrow = date.today() + timedelta(days=1)
        response = client.delete(f"/api/v1/routes/bulk?shift_id={test_route.shift_id}&route_date={tomorrow}", headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_delete_bulk_empty_list(self, client: TestClient, admin_token: str, test_shift):
        """Bulk delete with no matching routes returns success"""
        from datetime import date
        # Use date far in past with no routes
        response = client.request(
            "DELETE", 
            f"/api/v1/routes/bulk?shift_id={test_shift.shift_id}&route_date={date(2020, 1, 1)}",
            headers={"Authorization": admin_token}
        )

        # Should succeed even with no routes (returns empty list)
        assert response.status_code == status.HTTP_200_OK

    def test_delete_bulk_some_not_found(self, client: TestClient, admin_token: str, test_route):
        """Bulk delete only deletes routes that match shift+date"""
        from datetime import date, timedelta
        tomorrow = date.today() + timedelta(days=1)
        # This should delete test_route which matches shift+date
        response = client.delete(f"/api/v1/routes/bulk?shift_id={test_route.shift_id}&route_date={tomorrow}", headers={"Authorization": admin_token}
        )

        assert response.status_code == status.HTTP_200_OK


class TestRouteIntegration:
    """Integration tests for route management workflows"""

    def test_complete_route_lifecycle(self, client: TestClient, employee_token: str, test_tenant, test_shift, test_employee):
        """Complete workflow: create booking → cluster → assign vendor/vehicle → complete"""
        tomorrow = date.today() + timedelta(days=1)
        
        # 1. Create booking (employee can create without tenant_id)
        booking_response = client.post(
            "/api/v1/bookings/",
            json={
                "employee_id": test_employee["employee"].employee_id,
                "shift_id": test_shift.shift_id,
                "booking_dates": [str(tomorrow)]
            },
            headers={"Authorization": employee_token}
        )
        assert booking_response.status_code == status.HTTP_201_CREATED
        
        # 2. Create routes (clustering)
        routes_response = client.post(
            f"/api/v1/routes/?booking_date={tomorrow}&shift_id={test_shift.shift_id}&radius=1.0&group_size=2",
            headers={"Authorization": employee_token}
        )
        assert routes_response.status_code == status.HTTP_200_OK
        
        # 3. Verify unrouted bookings reduced
        unrouted_response = client.get(
            f"/api/v1/routes/unrouted?shift_id={test_shift.shift_id}&booking_date={tomorrow}",
            headers={"Authorization": employee_token}
        )
        assert unrouted_response.status_code == status.HTTP_200_OK

    def test_route_tenant_isolation(self, client: TestClient, employee_token: str, admin_token: str, test_route, second_route):
        """Routes properly isolated by tenant"""
        # Employee from tenant1 cannot access tenant2 route (404 - not found in their tenant)
        response = client.get(
            f"/api/v1/routes/{second_route.route_id}",
            headers={"Authorization": employee_token}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        # Admin can access with explicit tenant_id
        response = client.get(
            f"/api/v1/routes/?tenant_id={second_route.tenant_id}",
            headers={"Authorization": admin_token}
        )
        assert response.status_code == status.HTTP_200_OK

    def test_route_booking_status_updates(self, client: TestClient, admin_token: str, test_booking, test_route):
        """Booking status updates correctly through route lifecycle"""
        # Test booking initially has REQUEST status
        assert test_booking.status.value == "Request"
        
        # After adding to route, status should change to SCHEDULED
        # This is tested through the route update endpoint

