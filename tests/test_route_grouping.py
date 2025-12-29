"""
Comprehensive test suite for route grouping endpoints.

Tests cover:
- GET /api/v1/route-grouping/bookings - Get bookings by date/shift and generate clusters
- POST /api/v1/route-grouping/save-confirm - Save/confirm route groups
- POST /api/v1/route-grouping/merge - Merge multiple routes
- POST /api/v1/route-grouping/split - Split route into multiple routes
- PUT /api/v1/route-grouping/update - Update route with new bookings
- DELETE /api/v1/route-grouping/delete/{route_id} - Delete route
- GET /api/v1/route-grouping/routes - Get all routes for tenant
- GET /api/v1/route-grouping/routes/{route_id} - Get specific route details
"""

import pytest
from fastapi import status
from datetime import date, timedelta


class TestGetBookingsByDateAndShift:
    """Test GET /api/v1/route-grouping/bookings endpoint"""
    
    def test_get_bookings_with_clusters_success(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should retrieve bookings and generate route clusters"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        
        # Create multiple bookings with different locations for clustering
        bookings = []
        booking_date = date.today()
        locations = [
            (40.7580, -73.9855, "Times Square", 40.7489, -73.9680, "Grand Central"),
            (40.7614, -73.9776, "Rockefeller Center", 40.7489, -73.9680, "Grand Central"),
            (40.7812, -73.9665, "Central Park", 40.7489, -73.9680, "Grand Central"),
        ]
        
        for i, (pickup_lat, pickup_lon, pickup_loc, drop_lat, drop_lon, drop_loc) in enumerate(locations):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Cluster Employee {i}",
                email=f"cluster{i}@test.com",
                phone=f"100000000{i}",
                employee_code=f"CLUST{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            
            booking = Booking(
                tenant_id=test_tenant.tenant_id,
                employee_id=emp.employee_id,
                employee_code=emp.employee_code,
                shift_id=test_shift.shift_id,
                team_id=test_team.team_id,
                booking_date=booking_date,
                pickup_latitude=pickup_lat,
                pickup_longitude=pickup_lon,
                pickup_location=pickup_loc,
                drop_latitude=drop_lat,
                drop_longitude=drop_lon,
                drop_location=drop_loc,
                status=BookingStatusEnum.SCHEDULED
            )
            test_db.add(booking)
            bookings.append(booking)
        
        test_db.commit()
        
        response = client.get(
            "/api/v1/route-grouping/bookings",
            params={
                "booking_date": booking_date.isoformat(),
                "shift_id": test_shift.shift_id,
                "radius": 1.0,
                "group_size": 2
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "route_clusters" in data
        assert "total_bookings" in data
        assert "total_clusters" in data
        assert data["total_bookings"] == 3
    
    def test_get_bookings_no_bookings_found(self, client, admin_token, test_shift):
        """Should return 404 when no bookings exist"""
        future_date = date.today() + timedelta(days=365)
        
        response = client.get(
            "/api/v1/route-grouping/bookings",
            params={
                "booking_date": future_date.isoformat(),
                "shift_id": test_shift.shift_id
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_bookings_with_custom_parameters(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should handle custom radius and group_size parameters"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        
        booking_date = date.today()
        emp = Employee(
            tenant_id=test_tenant.tenant_id,
            role_id=3,
            team_id=test_team.team_id,
            name="Param Test Employee",
            email="param@test.com",
            phone="2000000000",
            employee_code="PARAM001",
            password="hashed",
            is_active=True
        )
        test_db.add(emp)
        test_db.flush()
        
        booking = Booking(
            tenant_id=test_tenant.tenant_id,
            employee_id=emp.employee_id,
            employee_code=emp.employee_code,
            shift_id=test_shift.shift_id,
            team_id=test_team.team_id,
            booking_date=booking_date,
            pickup_latitude=40.7580,
            pickup_longitude=-73.9855,
            pickup_location="Test Location",
            drop_latitude=40.7489,
            drop_longitude=-73.9680,
            drop_location="Test Drop",
            status=BookingStatusEnum.SCHEDULED
        )
        test_db.add(booking)
        test_db.commit()
        
        response = client.get(
            "/api/v1/route-grouping/bookings",
            params={
                "booking_date": booking_date.isoformat(),
                "shift_id": test_shift.shift_id,
                "radius": 2.5,
                "group_size": 5,
                "strict_grouping": True
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK


class TestSaveConfirmRoutes:
    """Test POST /api/v1/route-grouping/save-confirm endpoint"""
    
    def test_save_confirm_routes_success(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should save/confirm route groups successfully"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        
        # Create bookings
        booking_ids = []
        for i in range(3):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Route Employee {i}",
                email=f"route{i}@test.com",
                phone=f"300000000{i}",
                employee_code=f"ROUTE{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            
            booking = Booking(
                tenant_id=test_tenant.tenant_id,
                employee_id=emp.employee_id,
                employee_code=emp.employee_code,
                shift_id=test_shift.shift_id,
                team_id=test_team.team_id,
                booking_date=date.today(),
                pickup_latitude=40.7580,
                pickup_longitude=-73.9855,
                pickup_location=f"Pickup {i}",
                drop_latitude=40.7489,
                drop_longitude=-73.9680,
                drop_location=f"Drop {i}",
                status=BookingStatusEnum.SCHEDULED
            )
            test_db.add(booking)
            test_db.flush()
            booking_ids.append(booking.booking_id)
        
        test_db.commit()
        
        response = client.post(
            "/api/v1/route-grouping/save-confirm",
            params={"tenant_id": test_tenant.tenant_id},
            json={
                "groups": [
                    {"group_id": 1, "bookings": booking_ids[:2]},
                    {"group_id": 2, "bookings": booking_ids[2:]}
                ]
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        assert data[0]["route_id"] == "1"
        assert data[1]["route_id"] == "2"
        assert "estimations" in data[0]
        assert "bookings" in data[0]
    
    def test_save_confirm_routes_empty_groups(self, client, admin_token, test_tenant):
        """Should handle empty groups gracefully"""
        response = client.post(
            "/api/v1/route-grouping/save-confirm",
            params={"tenant_id": test_tenant.tenant_id},
            json={"groups": []},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 0
    
    def test_save_confirm_routes_invalid_booking_ids(self, client, admin_token, test_tenant):
        """Should skip groups with invalid booking IDs"""
        response = client.post(
            "/api/v1/route-grouping/save-confirm",
            params={"tenant_id": test_tenant.tenant_id},
            json={
                "groups": [
                    {"group_id": 1, "bookings": [99999, 88888]}
                ]
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 0


class TestMergeRoutes:
    """Test POST /api/v1/route-grouping/merge endpoint"""
    
    def test_merge_routes_success(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should merge multiple routes into one"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        from app.models.route_management import RouteManagement, RouteManagementBooking
        
        # Create bookings
        booking_ids = []
        for i in range(4):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Merge Employee {i}",
                email=f"merge{i}@test.com",
                phone=f"400000000{i}",
                employee_code=f"MERGE{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            
            booking = Booking(
                tenant_id=test_tenant.tenant_id,
                employee_id=emp.employee_id,
                employee_code=emp.employee_code,
                shift_id=test_shift.shift_id,
                team_id=test_team.team_id,
                booking_date=date.today(),
                pickup_latitude=40.7580 + (i * 0.01),
                pickup_longitude=-73.9855,
                pickup_location=f"Pickup {i}",
                drop_latitude=40.7489,
                drop_longitude=-73.9680,
                drop_location=f"Drop {i}",
                status=BookingStatusEnum.SCHEDULED
            )
            test_db.add(booking)
            test_db.flush()
            booking_ids.append(booking.booking_id)
        
        # Create two routes
        route1 = RouteManagement(
            route_id="merge-route-1",
            tenant_id=test_tenant.tenant_id,
            route_code="MERGE1",
            estimated_total_distance=10.0,
            estimated_total_time=30.0,
            is_active=True
        )
        test_db.add(route1)
        
        route2 = RouteManagement(
            route_id="merge-route-2",
            tenant_id=test_tenant.tenant_id,
            route_code="MERGE2",
            estimated_total_distance=12.0,
            estimated_total_time=35.0,
            is_active=True
        )
        test_db.add(route2)
        test_db.flush()
        
        # Add bookings to routes
        for i, booking_id in enumerate(booking_ids[:2]):
            rb = RouteManagementBooking(
                route_id="merge-route-1",
                booking_id=booking_id,
                stop_order=i + 1
            )
            test_db.add(rb)
        
        for i, booking_id in enumerate(booking_ids[2:]):
            rb = RouteManagementBooking(
                route_id="merge-route-2",
                booking_id=booking_id,
                stop_order=i + 1
            )
            test_db.add(rb)
        
        test_db.commit()
        
        response = client.post(
            "/api/v1/route-grouping/merge",
            params={"tenant_id": test_tenant.tenant_id},
            json={"route_ids": ["merge-route-1", "merge-route-2"]},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "merged-" in data["route_id"]
        assert len(data["bookings"]) == 4
        assert "estimations" in data
    
    def test_merge_routes_not_found(self, client, admin_token, test_tenant):
        """Should return 404 when route doesn't exist"""
        response = client.post(
            "/api/v1/route-grouping/merge",
            params={"tenant_id": test_tenant.tenant_id},
            json={"route_ids": ["nonexistent-route"]},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_merge_routes_single_route(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should handle merging a single route"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        from app.models.route_management import RouteManagement, RouteManagementBooking
        
        emp = Employee(
            tenant_id=test_tenant.tenant_id,
            role_id=3,
            team_id=test_team.team_id,
            name="Single Merge Employee",
            email="singlemerge@test.com",
            phone="5000000000",
            employee_code="SINGLE001",
            password="hashed",
            is_active=True
        )
        test_db.add(emp)
        test_db.flush()
        
        booking = Booking(
            tenant_id=test_tenant.tenant_id,
            employee_id=emp.employee_id,
            employee_code=emp.employee_code,
            shift_id=test_shift.shift_id,
            team_id=test_team.team_id,
            booking_date=date.today(),
            pickup_latitude=40.7580,
            pickup_longitude=-73.9855,
            pickup_location="Single Pickup",
            drop_latitude=40.7489,
            drop_longitude=-73.9680,
            drop_location="Single Drop",
            status=BookingStatusEnum.SCHEDULED
        )
        test_db.add(booking)
        test_db.flush()
        
        route = RouteManagement(
            route_id="single-merge-route",
            tenant_id=test_tenant.tenant_id,
            route_code="SINGLE",
            estimated_total_distance=5.0,
            estimated_total_time=15.0,
            is_active=True
        )
        test_db.add(route)
        test_db.flush()
        
        rb = RouteManagementBooking(
            route_id="single-merge-route",
            booking_id=booking.booking_id,
            stop_order=1
        )
        test_db.add(rb)
        test_db.commit()
        
        response = client.post(
            "/api/v1/route-grouping/merge",
            params={"tenant_id": test_tenant.tenant_id},
            json={"route_ids": ["single-merge-route"]},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["bookings"]) == 1


class TestSplitRoute:
    """Test POST /api/v1/route-grouping/split endpoint"""
    
    def test_split_route_success(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should split route into multiple routes"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        from app.models.route_management import RouteManagement, RouteManagementBooking
        
        # Create bookings
        booking_ids = []
        for i in range(4):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Split Employee {i}",
                email=f"split{i}@test.com",
                phone=f"600000000{i}",
                employee_code=f"SPLIT{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            
            booking = Booking(
                tenant_id=test_tenant.tenant_id,
                employee_id=emp.employee_id,
                employee_code=emp.employee_code,
                shift_id=test_shift.shift_id,
                team_id=test_team.team_id,
                booking_date=date.today(),
                pickup_latitude=40.7580 + (i * 0.01),
                pickup_longitude=-73.9855,
                pickup_location=f"Split Pickup {i}",
                drop_latitude=40.7489,
                drop_longitude=-73.9680,
                drop_location=f"Split Drop {i}",
                status=BookingStatusEnum.SCHEDULED
            )
            test_db.add(booking)
            test_db.flush()
            booking_ids.append(booking.booking_id)
        
        # Create route with all bookings
        route = RouteManagement(
            route_id="split-route-1",
            tenant_id=test_tenant.tenant_id,
            route_code="SPLIT1",
            estimated_total_distance=20.0,
            estimated_total_time=60.0,
            is_active=True
        )
        test_db.add(route)
        test_db.flush()
        
        for i, booking_id in enumerate(booking_ids):
            rb = RouteManagementBooking(
                route_id="split-route-1",
                booking_id=booking_id,
                stop_order=i + 1
            )
            test_db.add(rb)
        
        test_db.commit()
        
        response = client.post(
            "/api/v1/route-grouping/split",
            params={"tenant_id": test_tenant.tenant_id},
            json={
                "route_id": "split-route-1",
                "groups": [
                    booking_ids[:2],
                    booking_ids[2:]
                ]
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        assert data[0]["route_id"] == "split-route-1-split-1"
        assert data[1]["route_id"] == "split-route-1-split-2"
    
    def test_split_route_not_found(self, client, admin_token, test_tenant):
        """Should return 404 when route doesn't exist"""
        response = client.post(
            "/api/v1/route-grouping/split",
            params={"tenant_id": test_tenant.tenant_id},
            json={
                "route_id": "nonexistent-route",
                "groups": [[1, 2], [3, 4]]
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_split_route_empty_groups(self, client, admin_token, test_db, test_tenant):
        """Should handle empty split groups"""
        from app.models.route_management import RouteManagement
        
        route = RouteManagement(
            route_id="empty-split-route",
            tenant_id=test_tenant.tenant_id,
            route_code="EMPTY",
            estimated_total_distance=5.0,
            estimated_total_time=15.0,
            is_active=True
        )
        test_db.add(route)
        test_db.commit()
        
        response = client.post(
            "/api/v1/route-grouping/split",
            params={"tenant_id": test_tenant.tenant_id},
            json={
                "route_id": "empty-split-route",
                "groups": []
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 0


class TestUpdateRoute:
    """Test PUT /api/v1/route-grouping/update endpoint"""
    
    def test_update_route_success(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should update route with new bookings"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        from app.models.route_management import RouteManagement, RouteManagementBooking
        
        # Create bookings
        booking_ids = []
        for i in range(3):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Update Employee {i}",
                email=f"update{i}@test.com",
                phone=f"700000000{i}",
                employee_code=f"UPDATE{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            
            booking = Booking(
                tenant_id=test_tenant.tenant_id,
                employee_id=emp.employee_id,
                employee_code=emp.employee_code,
                shift_id=test_shift.shift_id,
                team_id=test_team.team_id,
                booking_date=date.today(),
                pickup_latitude=40.7580 + (i * 0.01),
                pickup_longitude=-73.9855,
                pickup_location=f"Update Pickup {i}",
                drop_latitude=40.7489,
                drop_longitude=-73.9680,
                drop_location=f"Update Drop {i}",
                status=BookingStatusEnum.SCHEDULED
            )
            test_db.add(booking)
            test_db.flush()
            booking_ids.append(booking.booking_id)
        
        # Create route with first booking
        route = RouteManagement(
            route_id="update-route-1",
            tenant_id=test_tenant.tenant_id,
            route_code="UPDATE1",
            estimated_total_distance=5.0,
            estimated_total_time=15.0,
            is_active=True
        )
        test_db.add(route)
        test_db.flush()
        
        rb = RouteManagementBooking(
            route_id="update-route-1",
            booking_id=booking_ids[0],
            stop_order=1
        )
        test_db.add(rb)
        test_db.commit()
        
        # Update route with additional bookings
        response = client.put(
            "/api/v1/route-grouping/update",
            json={
                "route_id": "update-route-1",
                "bookings": booking_ids[1:]
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["route_id"] == "update-route-1"
        assert len(data["bookings"]) == 3
    
    def test_update_route_not_found(self, client, admin_token):
        """Should return 404 when route doesn't exist"""
        response = client.put(
            "/api/v1/route-grouping/update",
            json={
                "route_id": "nonexistent-route",
                "bookings": [1, 2]
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_route_with_duplicates(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should handle duplicate booking IDs correctly"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        from app.models.route_management import RouteManagement, RouteManagementBooking
        
        emp = Employee(
            tenant_id=test_tenant.tenant_id,
            role_id=3,
            team_id=test_team.team_id,
            name="Duplicate Update Employee",
            email="dupupdate@test.com",
            phone="8000000000",
            employee_code="DUPUPD001",
            password="hashed",
            is_active=True
        )
        test_db.add(emp)
        test_db.flush()
        
        booking = Booking(
            tenant_id=test_tenant.tenant_id,
            employee_id=emp.employee_id,
            employee_code=emp.employee_code,
            shift_id=test_shift.shift_id,
            team_id=test_team.team_id,
            booking_date=date.today(),
            pickup_latitude=40.7580,
            pickup_longitude=-73.9855,
            pickup_location="Dup Pickup",
            drop_latitude=40.7489,
            drop_longitude=-73.9680,
            drop_location="Dup Drop",
            status=BookingStatusEnum.SCHEDULED
        )
        test_db.add(booking)
        test_db.flush()
        
        route = RouteManagement(
            route_id="dup-update-route",
            tenant_id=test_tenant.tenant_id,
            route_code="DUPUPD",
            estimated_total_distance=5.0,
            estimated_total_time=15.0,
            is_active=True
        )
        test_db.add(route)
        test_db.flush()
        
        rb = RouteManagementBooking(
            route_id="dup-update-route",
            booking_id=booking.booking_id,
            stop_order=1
        )
        test_db.add(rb)
        test_db.commit()
        
        # Try to add same booking again
        response = client.put(
            "/api/v1/route-grouping/update",
            json={
                "route_id": "dup-update-route",
                "bookings": [booking.booking_id]
            },
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["bookings"]) == 1  # No duplicate


class TestDeleteRoute:
    """Test DELETE /api/v1/route-grouping/delete/{route_id} endpoint"""
    
    def test_delete_route_success(self, client, admin_token, test_db, test_tenant):
        """Should soft delete route successfully"""
        from app.models.route_management import RouteManagement
        
        route = RouteManagement(
            route_id="delete-route-1",
            tenant_id=test_tenant.tenant_id,
            route_code="DELETE1",
            estimated_total_distance=10.0,
            estimated_total_time=30.0,
            is_active=True
        )
        test_db.add(route)
        test_db.commit()
        
        response = client.delete(
            f"/api/v1/route-grouping/delete/delete-route-1",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["deleted_route_id"] == "delete-route-1"
        
        # Verify route is soft deleted
        test_db.refresh(route)
        assert route.is_active is False
    
    def test_delete_route_not_found(self, client, admin_token):
        """Should return 404 when route doesn't exist"""
        response = client.delete(
            "/api/v1/route-grouping/delete/nonexistent-route",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_delete_route_with_bookings(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should delete route and its bookings"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        from app.models.route_management import RouteManagement, RouteManagementBooking
        
        emp = Employee(
            tenant_id=test_tenant.tenant_id,
            role_id=3,
            team_id=test_team.team_id,
            name="Delete Booking Employee",
            email="deletebook@test.com",
            phone="9000000000",
            employee_code="DELBOOK001",
            password="hashed",
            is_active=True
        )
        test_db.add(emp)
        test_db.flush()
        
        booking = Booking(
            tenant_id=test_tenant.tenant_id,
            employee_id=emp.employee_id,
            employee_code=emp.employee_code,
            shift_id=test_shift.shift_id,
            team_id=test_team.team_id,
            booking_date=date.today(),
            pickup_latitude=40.7580,
            pickup_longitude=-73.9855,
            pickup_location="Delete Pickup",
            drop_latitude=40.7489,
            drop_longitude=-73.9680,
            drop_location="Delete Drop",
            status=BookingStatusEnum.SCHEDULED
        )
        test_db.add(booking)
        test_db.flush()
        
        route = RouteManagement(
            route_id="delete-with-bookings",
            tenant_id=test_tenant.tenant_id,
            route_code="DELBOOK",
            estimated_total_distance=5.0,
            estimated_total_time=15.0,
            is_active=True
        )
        test_db.add(route)
        test_db.flush()
        
        rb = RouteManagementBooking(
            route_id="delete-with-bookings",
            booking_id=booking.booking_id,
            stop_order=1
        )
        test_db.add(rb)
        test_db.commit()
        
        response = client.delete(
            "/api/v1/route-grouping/delete/delete-with-bookings",
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK


class TestGetAllRoutes:
    """Test GET /api/v1/route-grouping/routes endpoint"""
    
    def test_get_all_routes_success(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should retrieve all active routes for tenant"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        from app.models.route_management import RouteManagement, RouteManagementBooking
        
        # Create bookings and routes
        for i in range(2):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"All Routes Employee {i}",
                email=f"allroutes{i}@test.com",
                phone=f"100000000{i}",
                employee_code=f"ALLR{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            
            booking = Booking(
                tenant_id=test_tenant.tenant_id,
                employee_id=emp.employee_id,
                employee_code=emp.employee_code,
                shift_id=test_shift.shift_id,
                team_id=test_team.team_id,
                booking_date=date.today(),
                pickup_latitude=40.7580,
                pickup_longitude=-73.9855,
                pickup_location=f"All Pickup {i}",
                drop_latitude=40.7489,
                drop_longitude=-73.9680,
                drop_location=f"All Drop {i}",
                status=BookingStatusEnum.SCHEDULED
            )
            test_db.add(booking)
            test_db.flush()
            
            route = RouteManagement(
                route_id=f"all-route-{i}",
                tenant_id=test_tenant.tenant_id,
                route_code=f"ALL{i}",
                estimated_total_distance=5.0 * (i + 1),
                estimated_total_time=15.0 * (i + 1),
                is_active=True
            )
            test_db.add(route)
            test_db.flush()
            
            rb = RouteManagementBooking(
                route_id=f"all-route-{i}",
                booking_id=booking.booking_id,
                stop_order=1
            )
            test_db.add(rb)
        
        test_db.commit()
        
        response = client.get(
            "/api/v1/route-grouping/routes",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "routes" in data
        assert "total_routes" in data
        assert data["total_routes"] >= 2
    
    def test_get_all_routes_no_routes(self, client, admin_token, test_tenant):
        """Should return empty list when no routes exist"""
        response = client.get(
            "/api/v1/route-grouping/routes",
            params={"tenant_id": "EMPTY_TENANT"},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_routes"] == 0
        assert len(data["routes"]) == 0
    
    def test_get_all_routes_filters_inactive(self, client, admin_token, test_db, test_tenant):
        """Should not return inactive routes"""
        from app.models.route_management import RouteManagement
        
        # Create active and inactive routes
        active_route = RouteManagement(
            route_id="active-filter-route",
            tenant_id=test_tenant.tenant_id,
            route_code="ACTIVE",
            estimated_total_distance=5.0,
            estimated_total_time=15.0,
            is_active=True
        )
        test_db.add(active_route)
        
        inactive_route = RouteManagement(
            route_id="inactive-filter-route",
            tenant_id=test_tenant.tenant_id,
            route_code="INACTIVE",
            estimated_total_distance=5.0,
            estimated_total_time=15.0,
            is_active=False
        )
        test_db.add(inactive_route)
        test_db.commit()
        
        response = client.get(
            "/api/v1/route-grouping/routes",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        route_ids = [r["route_id"] for r in data["routes"]]
        assert "active-filter-route" in route_ids
        assert "inactive-filter-route" not in route_ids


class TestGetRouteById:
    """Test GET /api/v1/route-grouping/routes/{route_id} endpoint"""
    
    def test_get_route_by_id_success(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Should retrieve specific route by ID"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        from app.models.route_management import RouteManagement, RouteManagementBooking
        
        emp = Employee(
            tenant_id=test_tenant.tenant_id,
            role_id=3,
            team_id=test_team.team_id,
            name="Get By ID Employee",
            email="getbyid@test.com",
            phone="1100000000",
            employee_code="GETID001",
            password="hashed",
            is_active=True
        )
        test_db.add(emp)
        test_db.flush()
        
        booking = Booking(
            tenant_id=test_tenant.tenant_id,
            employee_id=emp.employee_id,
            employee_code=emp.employee_code,
            shift_id=test_shift.shift_id,
            team_id=test_team.team_id,
            booking_date=date.today(),
            pickup_latitude=40.7580,
            pickup_longitude=-73.9855,
            pickup_location="GetID Pickup",
            drop_latitude=40.7489,
            drop_longitude=-73.9680,
            drop_location="GetID Drop",
            status=BookingStatusEnum.SCHEDULED
        )
        test_db.add(booking)
        test_db.flush()
        
        route = RouteManagement(
            route_id="get-by-id-route",
            tenant_id=test_tenant.tenant_id,
            route_code="GETID",
            estimated_total_distance=7.5,
            estimated_total_time=22.5,
            is_active=True
        )
        test_db.add(route)
        test_db.flush()
        
        rb = RouteManagementBooking(
            route_id="get-by-id-route",
            booking_id=booking.booking_id,
            stop_order=1,
            estimated_pickup_time="08:00",
            estimated_drop_time="08:30"
        )
        test_db.add(rb)
        test_db.commit()
        
        response = client.get(
            "/api/v1/route-grouping/routes/get-by-id-route",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["route_id"] == "get-by-id-route"
        assert len(data["bookings"]) == 1
        assert data["estimations"]["estimated_total_distance"] == 7.5
        assert data["estimations"]["estimated_total_time"] == 22.5
    
    def test_get_route_by_id_not_found(self, client, admin_token, test_tenant):
        """Should return 404 when route doesn't exist"""
        response = client.get(
            "/api/v1/route-grouping/routes/nonexistent-route",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_route_by_id_wrong_tenant(self, client, admin_token, test_db, test_tenant, second_tenant):
        """Should return 404 when route belongs to different tenant"""
        from app.models.route_management import RouteManagement
        
        route = RouteManagement(
            route_id="wrong-tenant-route",
            tenant_id=second_tenant.tenant_id,
            route_code="WRONG",
            estimated_total_distance=5.0,
            estimated_total_time=15.0,
            is_active=True
        )
        test_db.add(route)
        test_db.commit()
        
        response = client.get(
            "/api/v1/route-grouping/routes/wrong-tenant-route",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestRouteGroupingIntegration:
    """Integration tests for complete route grouping workflows"""
    
    def test_complete_route_workflow(self, client, admin_token, test_db, test_tenant, test_shift, test_team):
        """Test complete workflow: create, merge, split, update, delete"""
        from app.models.booking import Booking, BookingStatusEnum
        from app.models.employee import Employee
        
        # Step 1: Create bookings
        booking_ids = []
        for i in range(6):
            emp = Employee(
                tenant_id=test_tenant.tenant_id,
                role_id=3,
                team_id=test_team.team_id,
                name=f"Workflow Employee {i}",
                email=f"workflow{i}@test.com",
                phone=f"120000000{i}",
                employee_code=f"WORK{i}",
                password="hashed",
                is_active=True
            )
            test_db.add(emp)
            test_db.flush()
            
            booking = Booking(
                tenant_id=test_tenant.tenant_id,
                employee_id=emp.employee_id,
                employee_code=emp.employee_code,
                shift_id=test_shift.shift_id,
                team_id=test_team.team_id,
                booking_date=date.today(),
                pickup_latitude=40.7580 + (i * 0.01),
                pickup_longitude=-73.9855,
                pickup_location=f"Workflow Pickup {i}",
                drop_latitude=40.7489,
                drop_longitude=-73.9680,
                drop_location=f"Workflow Drop {i}",
                status=BookingStatusEnum.SCHEDULED
            )
            test_db.add(booking)
            test_db.flush()
            booking_ids.append(booking.booking_id)
        
        test_db.commit()
        
        # Step 2: Save/confirm routes
        save_response = client.post(
            "/api/v1/route-grouping/save-confirm",
            params={"tenant_id": test_tenant.tenant_id},
            json={
                "groups": [
                    {"group_id": 100, "bookings": booking_ids[:3]},
                    {"group_id": 101, "bookings": booking_ids[3:]}
                ]
            },
            headers={"Authorization": admin_token}
        )
        assert save_response.status_code == status.HTTP_200_OK
        
        # Step 3: Merge routes
        merge_response = client.post(
            "/api/v1/route-grouping/merge",
            params={"tenant_id": test_tenant.tenant_id},
            json={"route_ids": ["100", "101"]},
            headers={"Authorization": admin_token}
        )
        assert merge_response.status_code == status.HTTP_200_OK
        merged_route_id = merge_response.json()["route_id"]
        
        # Step 4: Get all routes
        get_all_response = client.get(
            "/api/v1/route-grouping/routes",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        assert get_all_response.status_code == status.HTTP_200_OK
        
        # Step 5: Get specific route
        get_route_response = client.get(
            f"/api/v1/route-grouping/routes/{merged_route_id}",
            params={"tenant_id": test_tenant.tenant_id},
            headers={"Authorization": admin_token}
        )
        assert get_route_response.status_code == status.HTTP_200_OK
        
        # Step 6: Delete route
        delete_response = client.delete(
            f"/api/v1/route-grouping/delete/{merged_route_id}",
            headers={"Authorization": admin_token}
        )
        assert delete_response.status_code == status.HTTP_200_OK

