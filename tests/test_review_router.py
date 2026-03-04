"""
tests/test_review_router.py
============================
Comprehensive edge-case tests for the ride-review system.
Covers all 9 endpoints with happy paths + realistic edge cases.

Fixture dependencies (from conftest.py):
  client, test_db, employee_token, admin_token, test_tenant,
  employee_user, test_driver, test_vehicle, test_shift
"""
import pytest
from datetime import date, timedelta
from app.models.booking import Booking, BookingStatusEnum
from app.models.review import RideReview, ReviewTag, ReviewTagTypeEnum
from app.models.route_management import RouteManagement, RouteManagementBooking, RouteManagementStatusEnum


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

def _make_completed_booking(db, tenant_id, employee_id, shift_id, booking_id):
    """Helper: insert a COMPLETED booking and flush (no commit)."""
    bk = Booking(
        booking_id=booking_id,
        tenant_id=tenant_id,
        employee_id=employee_id,
        employee_code="EMP_TEST",
        shift_id=shift_id,
        booking_date=date.today() - timedelta(days=1),
        status=BookingStatusEnum.COMPLETED,
        pickup_latitude=40.71,
        pickup_longitude=-74.00,
        drop_latitude=40.75,
        drop_longitude=-73.98,
        pickup_location="Home",
        drop_location="Office",
    )
    db.add(bk)
    db.commit()
    db.refresh(bk)
    return bk


def _make_route_with_booking(db, tenant_id, shift_id, driver_id, vehicle_id,
                              booking_id, route_id=5001):
    """Helper: route + route_management_booking link for a completed booking."""
    route = RouteManagement(
        route_id=route_id,
        tenant_id=tenant_id,
        shift_id=shift_id,
        route_code=f"RT-{route_id}",
        estimated_total_time=30.0,
        estimated_total_distance=10.0,
        buffer_time=5.0,
        status=RouteManagementStatusEnum.COMPLETED,
        assigned_driver_id=driver_id,
        assigned_vehicle_id=vehicle_id,
    )
    db.add(route)
    db.flush()
    rb = RouteManagementBooking(
        route_id=route_id,
        booking_id=booking_id,
        order_id=1,
        estimated_pick_up_time="08:00:00",
        estimated_distance=5.0,
    )
    db.add(rb)
    db.commit()
    return route


# ----------------------------------------------------------------
# POST /reviews/tags  (admin creates tag)
# DELETE /reviews/tags/{tag_id}  (admin deactivates tag)
# GET /reviews/tags  (public tag picker)
# ----------------------------------------------------------------

class TestTagManagement:

    def test_get_global_tags_no_auth(self, client):
        """GET /reviews/tags requires no auth and returns global tags (seeded or empty)."""
        resp = client.get("/api/v1/reviews/tags")
        assert resp.status_code == 200
        body = resp.json()
        assert "driver_tags" in body["data"]
        assert "vehicle_tags" in body["data"]

    def test_create_driver_tag(self, client, admin_token, test_tenant):
        resp = client.post(
            "/api/v1/reviews/tags",
            json={"tag_type": "driver", "tag_name": "Very Punctual", "display_order": 1},
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["tag_name"] == "Very Punctual"
        assert data["tag_type"] == "driver"
        assert data["is_active"] is True

    def test_create_vehicle_tag(self, client, admin_token, test_tenant):
        resp = client.post(
            "/api/v1/reviews/tags",
            json={"tag_type": "vehicle", "tag_name": "Spotless Clean", "display_order": 2},
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["tag_type"] == "vehicle"

    def test_create_tag_invalid_type(self, client, admin_token, test_tenant):
        """tag_type must be 'driver' or 'vehicle'."""
        resp = client.post(
            "/api/v1/reviews/tags",
            json={"tag_type": "helicopter", "tag_name": "Weird Tag", "display_order": 1},
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 422

    def test_create_tag_no_auth(self, client):
        resp = client.post(
            "/api/v1/reviews/tags",
            json={"tag_type": "driver", "tag_name": "NoAuth", "display_order": 1},
        )
        assert resp.status_code == 401

    def test_delete_own_tenant_tag(self, client, test_db, admin_token, test_tenant):
        """Admin can deactivate a tag they created for their tenant."""
        tag = ReviewTag(
            tenant_id=test_tenant.tenant_id,
            tag_type=ReviewTagTypeEnum.DRIVER,
            tag_name="OldTag",
            display_order=99,
        )
        test_db.add(tag)
        test_db.commit()
        test_db.refresh(tag)

        resp = client.delete(
            f"/api/v1/reviews/tags/{tag.tag_id}",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        test_db.refresh(tag)
        assert tag.is_active is False

    def test_delete_nonexistent_tag(self, client, admin_token):
        resp = client.delete(
            "/api/v1/reviews/tags/999999",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 404

    def test_delete_global_tag_denied(self, client, test_db, admin_token):
        """Global tags (tenant_id=NULL) cannot be deleted by a tenant admin."""
        global_tag = ReviewTag(
            tenant_id=None,          # global
            tag_type=ReviewTagTypeEnum.VEHICLE,
            tag_name="GlobalVehicleTag",
            display_order=1,
        )
        test_db.add(global_tag)
        test_db.commit()
        test_db.refresh(global_tag)

        resp = client.delete(
            f"/api/v1/reviews/tags/{global_tag.tag_id}",
            headers={"Authorization": admin_token},
        )
        # admin_token tenant is TEST001; global tag has tenant_id=NULL
        assert resp.status_code == 404

    def test_get_tags_with_tenant_filter(self, client, test_db, test_tenant):
        """?tenant_id= includes both global and tenant-scoped tags."""
        global_tag = ReviewTag(tenant_id=None, tag_type=ReviewTagTypeEnum.DRIVER, tag_name="GlobalDrv", display_order=1)
        tenant_tag = ReviewTag(tenant_id=test_tenant.tenant_id, tag_type=ReviewTagTypeEnum.DRIVER, tag_name="TenantDrv", display_order=2)
        test_db.add_all([global_tag, tenant_tag])
        test_db.commit()

        resp = client.get(f"/api/v1/reviews/tags?tenant_id={test_tenant.tenant_id}")
        assert resp.status_code == 200
        driver_tags = resp.json()["data"]["driver_tags"]
        assert "GlobalDrv" in driver_tags
        assert "TenantDrv" in driver_tags


# ----------------------------------------------------------------
# POST /employee/bookings/{booking_id}/review
# ----------------------------------------------------------------

class TestSubmitReviewByBooking:

    def test_happy_path_full_review(self, client, test_db, employee_token, employee_user, test_shift):
        """Employee submits a full review on their completed booking."""
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 9001)

        resp = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={
                "overall_rating": 5,
                "driver_rating": 4,
                "driver_tags": ["Punctual", "Friendly"],
                "driver_comment": "Great driver!",
                "vehicle_rating": 5,
                "vehicle_tags": ["Clean"],
                "vehicle_comment": "Spotless",
            },
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["booking_id"] == bk.booking_id
        assert data["overall_rating"] == 5
        assert data["driver_rating"] == 4
        assert data["driver_tags"] == ["Punctual", "Friendly"]

    def test_partial_review_only_overall(self, client, test_db, employee_token, employee_user, test_shift):
        """Sending only overall_rating is valid (all fields optional)."""
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 9002)

        resp = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={"overall_rating": 3},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["overall_rating"] == 3
        assert data["driver_rating"] is None
        assert data["driver_tags"] == []

    def test_free_form_custom_tags_allowed(self, client, test_db, employee_token, employee_user, test_shift):
        """Any free-form word is accepted as a tag — no server-side enforcement."""
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 9003)

        resp = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={"driver_tags": ["Amazing human being", "Drives like a pro"], "driver_rating": 5},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 201
        assert "Amazing human being" in resp.json()["data"]["driver_tags"]

    def test_empty_payload_rejected(self, client, test_db, employee_token, employee_user, test_shift):
        """Pydantic model_validator: at least one field required."""
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 9004)

        resp = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 422

    def test_star_rating_out_of_range_above(self, client, test_db, employee_token, employee_user, test_shift):
        """overall_rating > 5 should be rejected."""
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 9005)

        resp = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={"overall_rating": 6},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 422

    def test_star_rating_out_of_range_below(self, client, test_db, employee_token, employee_user, test_shift):
        """overall_rating < 1 should be rejected."""
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 9006)

        resp = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={"overall_rating": 0},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 422

    def test_booking_not_completed(self, client, test_db, employee_token, employee_user, test_shift):
        """Review on a REQUEST booking returns 400."""
        emp = employee_user["employee"]
        bk = Booking(
            booking_id=9010,
            tenant_id=emp.tenant_id,
            employee_id=emp.employee_id,
            employee_code="EMP_TEST",
            shift_id=test_shift.shift_id,
            booking_date=date.today() + timedelta(days=1),
            status=BookingStatusEnum.REQUEST,
            pickup_latitude=40.71, pickup_longitude=-74.00,
            drop_latitude=40.75, drop_longitude=-73.98,
            pickup_location="Home", drop_location="Office",
        )
        test_db.add(bk)
        test_db.commit()

        resp = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={"overall_rating": 4},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 400
        assert "BOOKING_NOT_COMPLETED" in str(resp.json())

    def test_wrong_employee_gets_404(self, client, test_db, employee_token, test_tenant, test_shift):
        """Employee trying to review another employee's booking gets 404."""
        other_bk = Booking(
            booking_id=9011,
            tenant_id=test_tenant.tenant_id,
            employee_id=99999,           # different employee
            employee_code="OTHER_EMP",
            shift_id=test_shift.shift_id,
            booking_date=date.today() - timedelta(days=1),
            status=BookingStatusEnum.COMPLETED,
            pickup_latitude=40.71, pickup_longitude=-74.00,
            drop_latitude=40.75, drop_longitude=-73.98,
            pickup_location="Home", drop_location="Office",
        )
        test_db.add(other_bk)
        test_db.commit()

        resp = client.post(
            f"/api/v1/employee/bookings/{other_bk.booking_id}/review",
            json={"overall_rating": 4},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 404

    def test_duplicate_review_returns_409(self, client, test_db, employee_token, employee_user, test_shift):
        """Second review on same booking returns 409 REVIEW_ALREADY_EXISTS."""
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 9012)

        payload = {"overall_rating": 4}
        r1 = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json=payload,
            headers={"Authorization": employee_token},
        )
        assert r1.status_code == 201

        r2 = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json=payload,
            headers={"Authorization": employee_token},
        )
        assert r2.status_code == 409
        assert "REVIEW_ALREADY_EXISTS" in str(r2.json())

    def test_no_auth_returns_401(self, client, test_db, employee_user, test_shift):
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 9013)
        resp = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={"overall_rating": 3},
        )
        assert resp.status_code == 401

    def test_nonexistent_booking_returns_404(self, client, employee_token):
        resp = client.post(
            "/api/v1/employee/bookings/9999999/review",
            json={"overall_rating": 3},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 404


# ----------------------------------------------------------------
# POST /employee/routes/{route_id}/review
# ----------------------------------------------------------------

class TestSubmitReviewByRoute:

    def test_happy_path_by_route(self, client, test_db, employee_token, employee_user,
                                  test_shift, test_driver, test_vehicle):
        """Employee submits review via route_id; system auto-finds booking."""
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 8001)
        _make_route_with_booking(
            test_db, emp.tenant_id, test_shift.shift_id,
            test_driver.driver_id, test_vehicle.vehicle_id,
            bk.booking_id, route_id=8001,
        )

        resp = client.post(
            "/api/v1/employee/routes/8001/review",
            json={"driver_rating": 5, "driver_tags": ["Safe Driver"]},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["route_id"] == 8001
        assert data["driver_id"] == test_driver.driver_id

    def test_route_not_in_tenant_returns_404(self, client, employee_token):
        """Route that doesn't exist returns 404."""
        resp = client.post(
            "/api/v1/employee/routes/9999999/review",
            json={"overall_rating": 4},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 404
        assert "ROUTE_NOT_FOUND" in str(resp.json())

    def test_employee_not_on_route_returns_404(self, client, test_db, employee_token,
                                                employee_user, test_shift, test_driver, test_vehicle):
        """Route exists but this employee has no booking on it."""
        emp = employee_user["employee"]
        # Create route but link booking to DIFFERENT employee
        other_bk = Booking(
            booking_id=8010,
            tenant_id=emp.tenant_id,
            employee_id=99998,
            employee_code="OTHER",
            shift_id=test_shift.shift_id,
            booking_date=date.today() - timedelta(days=1),
            status=BookingStatusEnum.COMPLETED,
            pickup_latitude=40.71, pickup_longitude=-74.00,
            drop_latitude=40.75, drop_longitude=-73.98,
            pickup_location="A", drop_location="B",
        )
        test_db.add(other_bk)
        test_db.commit()
        _make_route_with_booking(
            test_db, emp.tenant_id, test_shift.shift_id,
            test_driver.driver_id, test_vehicle.vehicle_id,
            other_bk.booking_id, route_id=8011,
        )

        resp = client.post(
            "/api/v1/employee/routes/8011/review",
            json={"overall_rating": 4},
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 404
        assert "BOOKING_NOT_FOUND_ON_ROUTE" in str(resp.json())

    def test_duplicate_review_via_route_returns_409(self, client, test_db, employee_token,
                                                     employee_user, test_shift, test_driver, test_vehicle):
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 8020)
        _make_route_with_booking(
            test_db, emp.tenant_id, test_shift.shift_id,
            test_driver.driver_id, test_vehicle.vehicle_id,
            bk.booking_id, route_id=8021,
        )

        payload = {"overall_rating": 5}
        r1 = client.post("/api/v1/employee/routes/8021/review", json=payload,
                         headers={"Authorization": employee_token})
        assert r1.status_code == 201

        r2 = client.post("/api/v1/employee/routes/8021/review", json=payload,
                         headers={"Authorization": employee_token})
        assert r2.status_code == 409


# ----------------------------------------------------------------
# GET /employee/bookings/{booking_id}/review
# ----------------------------------------------------------------

class TestGetMyReview:

    def test_get_own_review(self, client, test_db, employee_token, employee_user, test_shift):
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 7001)
        rev = RideReview(
            tenant_id=emp.tenant_id,
            booking_id=bk.booking_id,
            employee_id=emp.employee_id,
            overall_rating=4,
            driver_tags=["Polite"],
        )
        test_db.add(rev)
        test_db.commit()

        resp = client.get(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["overall_rating"] == 4

    def test_no_review_yet_returns_404(self, client, test_db, employee_token, employee_user, test_shift):
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 7002)

        resp = client.get(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 404
        assert "REVIEW_NOT_FOUND" in str(resp.json())

    def test_wrong_booking_returns_404(self, client, test_db, employee_token, test_tenant, test_shift):
        """Booking that belongs to another employee returns 404 to employee."""
        other_bk = Booking(
            booking_id=7010,
            tenant_id=test_tenant.tenant_id,
            employee_id=99999,
            employee_code="OTHER",
            shift_id=test_shift.shift_id,
            booking_date=date.today() - timedelta(days=1),
            status=BookingStatusEnum.COMPLETED,
            pickup_latitude=40.71, pickup_longitude=-74.00,
            drop_latitude=40.75, drop_longitude=-73.98,
            pickup_location="A", drop_location="B",
        )
        test_db.add(other_bk)
        test_db.commit()

        resp = client.get(
            f"/api/v1/employee/bookings/{other_bk.booking_id}/review",
            headers={"Authorization": employee_token},
        )
        assert resp.status_code == 404


# ----------------------------------------------------------------
# GET /bookings/{booking_id}/review  (admin)
# ----------------------------------------------------------------

class TestAdminGetBookingReview:

    def test_admin_reads_any_booking_review(self, client, test_db, admin_token,
                                             employee_user, test_shift):
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 6001)
        rev = RideReview(
            tenant_id=emp.tenant_id,
            booking_id=bk.booking_id,
            employee_id=emp.employee_id,
            driver_rating=3,
        )
        test_db.add(rev)
        test_db.commit()

        resp = client.get(
            f"/api/v1/bookings/{bk.booking_id}/review",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["driver_rating"] == 3

    def test_admin_cross_tenant_booking_returns_404(self, client, test_db, admin_token,
                                                     test_db_second_tenant_booking, test_shift):
        """Booking from a different tenant is invisible to admin of first tenant."""
        other_bk = Booking(
            booking_id=6010,
            tenant_id="TEST002",     # different tenant
            employee_id=99990,
            employee_code="X",
            shift_id=test_shift.shift_id,
            booking_date=date.today() - timedelta(days=1),
            status=BookingStatusEnum.COMPLETED,
            pickup_latitude=40.71, pickup_longitude=-74.00,
            drop_latitude=40.75, drop_longitude=-73.98,
            pickup_location="A", drop_location="B",
        )
        test_db.add(other_bk)
        test_db.commit()

        resp = client.get(
            "/api/v1/bookings/6010/review",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 404

    def test_no_review_on_booking_returns_404(self, client, test_db, admin_token,
                                               employee_user, test_shift):
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 6020)

        resp = client.get(
            f"/api/v1/bookings/{bk.booking_id}/review",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 404
        assert "REVIEW_NOT_FOUND" in str(resp.json())

    def test_no_auth_returns_401(self, client, test_db, employee_user, test_shift):
        emp = employee_user["employee"]
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 6030)
        resp = client.get(f"/api/v1/bookings/{bk.booking_id}/review")
        assert resp.status_code == 401


# ----------------------------------------------------------------
# GET /drivers/{driver_id}/reviews  (admin)
# ----------------------------------------------------------------

class TestDriverReviews:

    def _seed_driver_reviews(self, db, tenant_id, driver_id, employee_id, shift_id, n=3):
        """Seed n reviews for a driver and return them."""
        reviews = []
        for i in range(n):
            bk = _make_completed_booking(db, tenant_id, employee_id, shift_id, 5000 + i)
            rev = RideReview(
                tenant_id=tenant_id,
                booking_id=bk.booking_id,
                employee_id=employee_id,
                driver_id=driver_id,
                driver_rating=(i % 5) + 1,
                driver_tags=["Tag{}".format(i)],
                driver_comment="Comment {}".format(i),
            )
            db.add(rev)
        db.commit()
        return reviews

    def test_driver_reviews_summary(self, client, test_db, admin_token,
                                     test_driver, employee_user, test_shift):
        emp = employee_user["employee"]
        self._seed_driver_reviews(
            test_db, emp.tenant_id, test_driver.driver_id, emp.employee_id, test_shift.shift_id, n=3
        )

        resp = client.get(
            f"/api/v1/drivers/{test_driver.driver_id}/reviews",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["summary"]["driver_id"] == test_driver.driver_id
        assert body["summary"]["total_reviews"] == 3
        assert body["summary"]["average_rating"] is not None
        assert "pagination" in body

    def test_driver_reviews_pagination(self, client, test_db, admin_token,
                                        test_driver, employee_user, test_shift):
        emp = employee_user["employee"]
        self._seed_driver_reviews(
            test_db, emp.tenant_id, test_driver.driver_id, emp.employee_id, test_shift.shift_id, n=5
        )

        resp = client.get(
            f"/api/v1/drivers/{test_driver.driver_id}/reviews?page=1&per_page=2",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert len(body["reviews"]) == 2
        assert body["pagination"]["pages"] == 3   # 5 reviews / 2 per page = 3

    def test_driver_reviews_date_filter(self, client, test_db, admin_token,
                                         test_driver, employee_user, test_shift):
        """start_date in the future should return 0 reviews."""
        emp = employee_user["employee"]
        self._seed_driver_reviews(
            test_db, emp.tenant_id, test_driver.driver_id, emp.employee_id, test_shift.shift_id, n=2
        )
        future = (date.today() + timedelta(days=365)).isoformat()

        resp = client.get(
            f"/api/v1/drivers/{test_driver.driver_id}/reviews?start_date={future}",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["summary"]["total_reviews"] == 0

    def test_driver_not_in_tenant_returns_404(self, client, admin_token):
        resp = client.get(
            "/api/v1/drivers/9999999/reviews",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 404

    def test_driver_no_reviews_returns_empty(self, client, test_db, admin_token,
                                              test_driver, employee_user):
        """Driver exists but has zero reviews — should return total=0, not error."""
        resp = client.get(
            f"/api/v1/drivers/{test_driver.driver_id}/reviews",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        summary = resp.json()["data"]["summary"]
        assert summary["total_reviews"] == 0
        assert summary["average_rating"] is None

    def test_driver_reviews_tag_counts(self, client, test_db, admin_token,
                                        test_driver, employee_user, test_shift):
        """tag_counts should aggregate frequencies across all reviews."""
        emp = employee_user["employee"]
        for i, tags in enumerate([["Fast", "Polite"], ["Fast"], ["Polite", "Safe"]]):
            bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 4100 + i)
            rev = RideReview(
                tenant_id=emp.tenant_id, booking_id=bk.booking_id,
                employee_id=emp.employee_id, driver_id=test_driver.driver_id,
                driver_rating=5, driver_tags=tags,
            )
            test_db.add(rev)
        test_db.commit()

        resp = client.get(
            f"/api/v1/drivers/{test_driver.driver_id}/reviews",
            headers={"Authorization": admin_token},
        )
        tag_counts = resp.json()["data"]["summary"]["tag_counts"]
        assert tag_counts.get("Fast") == 2
        assert tag_counts.get("Polite") == 2
        assert tag_counts.get("Safe") == 1


# ----------------------------------------------------------------
# GET /vehicles/{vehicle_id}/reviews  (admin)
# ----------------------------------------------------------------

class TestVehicleReviews:

    def _seed_vehicle_reviews(self, db, tenant_id, vehicle_id, employee_id, shift_id, n=3):
        for i in range(n):
            bk = _make_completed_booking(db, tenant_id, employee_id, shift_id, 3000 + i)
            rev = RideReview(
                tenant_id=tenant_id,
                booking_id=bk.booking_id,
                employee_id=employee_id,
                vehicle_id=vehicle_id,
                vehicle_rating=(i % 5) + 1,
                vehicle_tags=["VTag{}".format(i)],
            )
            db.add(rev)
        db.commit()

    def test_vehicle_reviews_summary(self, client, test_db, admin_token,
                                      test_vehicle, employee_user, test_shift):
        emp = employee_user["employee"]
        self._seed_vehicle_reviews(
            test_db, emp.tenant_id, test_vehicle.vehicle_id, emp.employee_id, test_shift.shift_id, n=3
        )

        resp = client.get(
            f"/api/v1/vehicles/{test_vehicle.vehicle_id}/reviews",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["summary"]["vehicle_id"] == test_vehicle.vehicle_id
        assert body["summary"]["total_reviews"] == 3

    def test_vehicle_not_found_returns_404(self, client, admin_token):
        resp = client.get(
            "/api/v1/vehicles/9999999/reviews",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 404

    def test_vehicle_no_reviews_empty(self, client, test_db, admin_token,
                                       test_vehicle, employee_user):
        resp = client.get(
            f"/api/v1/vehicles/{test_vehicle.vehicle_id}/reviews",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["summary"]["total_reviews"] == 0

    def test_vehicle_reviews_route_filter(self, client, test_db, admin_token,
                                           test_vehicle, employee_user, test_shift, test_driver):
        """?route_id= only returns reviews for that route."""
        emp = employee_user["employee"]
        # Route 3001: has review
        bk1 = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 3100)
        _make_route_with_booking(test_db, emp.tenant_id, test_shift.shift_id,
                                  test_driver.driver_id, test_vehicle.vehicle_id, bk1.booking_id, 3001)
        rev1 = RideReview(
            tenant_id=emp.tenant_id, booking_id=bk1.booking_id,
            employee_id=emp.employee_id, vehicle_id=test_vehicle.vehicle_id,
            vehicle_rating=5, route_id=3001,
        )
        # Route 3002: has review (different route)
        bk2 = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 3101)
        _make_route_with_booking(test_db, emp.tenant_id, test_shift.shift_id,
                                  test_driver.driver_id, test_vehicle.vehicle_id, bk2.booking_id, 3002)
        rev2 = RideReview(
            tenant_id=emp.tenant_id, booking_id=bk2.booking_id,
            employee_id=emp.employee_id, vehicle_id=test_vehicle.vehicle_id,
            vehicle_rating=3, route_id=3002,
        )
        test_db.add_all([rev1, rev2])
        test_db.commit()

        resp = client.get(
            f"/api/v1/vehicles/{test_vehicle.vehicle_id}/reviews?route_id=3001",
            headers={"Authorization": admin_token},
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["summary"]["total_reviews"] == 1


# ----------------------------------------------------------------
# Full end-to-end cycle
# ----------------------------------------------------------------

class TestFullCycle:
    """
    Simulates the real-world flow:
      Admin creates tag -> Employee completes ride -> Employee reviews ->
      Admin reads review -> Admin checks driver summary -> Admin checks vehicle summary
    """

    def test_full_review_lifecycle(self, client, test_db, admin_token, employee_token,
                                    employee_user, test_shift, test_driver, test_vehicle):
        emp = employee_user["employee"]

        # 1. Admin creates driver tag
        r1 = client.post(
            "/api/v1/reviews/tags",
            json={"tag_type": "driver", "tag_name": "On Time", "display_order": 1},
            headers={"Authorization": admin_token},
        )
        assert r1.status_code == 201

        # 2. Employee sees tag in picker
        r2 = client.get(f"/api/v1/reviews/tags?tenant_id={emp.tenant_id}")
        assert r2.status_code == 200
        assert "On Time" in r2.json()["data"]["driver_tags"]

        # 3. Create a completed booking linked to a route with driver+vehicle
        bk = _make_completed_booking(test_db, emp.tenant_id, emp.employee_id, test_shift.shift_id, 1001)
        _make_route_with_booking(
            test_db, emp.tenant_id, test_shift.shift_id,
            test_driver.driver_id, test_vehicle.vehicle_id,
            bk.booking_id, route_id=1001,
        )

        # 4. Employee submits review using booking_id
        r3 = client.post(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            json={
                "overall_rating": 5,
                "driver_rating": 5,
                "driver_tags": ["On Time", "Super helpful"],   # mix of suggested + custom
                "driver_comment": "Excellent driver!",
                "vehicle_rating": 4,
                "vehicle_tags": ["Clean"],
            },
            headers={"Authorization": employee_token},
        )
        assert r3.status_code == 201
        review_data = r3.json()["data"]
        assert review_data["driver_id"] == test_driver.driver_id
        assert review_data["vehicle_id"] == test_vehicle.vehicle_id

        # 5. Employee reads their own review back
        r4 = client.get(
            f"/api/v1/employee/bookings/{bk.booking_id}/review",
            headers={"Authorization": employee_token},
        )
        assert r4.status_code == 200
        assert r4.json()["data"]["overall_rating"] == 5

        # 6. Admin reads the review for that booking
        r5 = client.get(
            f"/api/v1/bookings/{bk.booking_id}/review",
            headers={"Authorization": admin_token},
        )
        assert r5.status_code == 200
        assert r5.json()["data"]["driver_comment"] == "Excellent driver!"

        # 7. Admin gets driver summary — should have 1 review, avg=5
        r6 = client.get(
            f"/api/v1/drivers/{test_driver.driver_id}/reviews",
            headers={"Authorization": admin_token},
        )
        assert r6.status_code == 200
        summary = r6.json()["data"]["summary"]
        assert summary["total_reviews"] == 1
        assert summary["average_rating"] == 5.0

        # 8. Admin gets vehicle summary — should have 1 review, avg=4
        r7 = client.get(
            f"/api/v1/vehicles/{test_vehicle.vehicle_id}/reviews",
            headers={"Authorization": admin_token},
        )
        assert r7.status_code == 200
        v_summary = r7.json()["data"]["summary"]
        assert v_summary["total_reviews"] == 1
        assert v_summary["average_rating"] == 4.0

        # 9. Admin deactivates the tag
        tag_id = r1.json()["data"]["tag_id"]
        r8 = client.delete(
            f"/api/v1/reviews/tags/{tag_id}",
            headers={"Authorization": admin_token},
        )
        assert r8.status_code == 200

        # 10. Tag no longer appears in picker
        r9 = client.get(f"/api/v1/reviews/tags?tenant_id={emp.tenant_id}")
        assert "On Time" not in r9.json()["data"]["driver_tags"]


# ----------------------------------------------------------------
# Fixture: dummy second-tenant booking (used in admin cross-tenant test)
# ----------------------------------------------------------------
@pytest.fixture(scope="function")
def test_db_second_tenant_booking(test_db):
    """Not a real fixture body -- just prevents NameError in the class."""
    return test_db
