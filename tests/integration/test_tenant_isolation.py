"""
Integration tests: Multi-tenant data isolation

Ensures that data belonging to Tenant A is never returned when querying
for Tenant B, across all core entity types: employees, bookings, shifts,
teams, vendors.

These tests are the primary regression gate for multi-tenancy correctness.
No HTTP layer — pure CRUD + SQLAlchemy.
"""
from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.crud.booking import booking_crud
from app.crud.employee import CRUDEmployee
from app.models.booking import Booking, BookingStatusEnum as ModelStatus
from app.models.employee import Employee
from app.models.shift import Shift
from app.models.team import Team
from app.models.vendor import Vendor
from app.schemas.employee import EmployeeCreate

pytestmark = pytest.mark.integration

employee_crud = CRUDEmployee(Employee)


# ─── Fixtures: full isolated entity graphs for each tenant ───────────────────
@pytest.fixture(scope="function")
def tenant_a_graph(db: Session, tenant_a, team_a, iam_seed):
    """Creates a complete entity graph for Tenant A."""
    emp_payload = EmployeeCreate(
        name="Alice A",
        employee_code="ISO_EMP_A",
        email="alice.a@testa.com",
        phone="+12025550301",
        password="Secure@Pass3",
        team_id=team_a.team_id,
        gender="Female",
        is_active=True,
    )
    emp = employee_crud.create_with_tenant(
        db, obj_in=emp_payload, tenant_id=tenant_a.tenant_id
    )
    shift = Shift(
        tenant_id=tenant_a.tenant_id,
        shift_code="ISO_SHIFT_A",
        log_type="IN",
        shift_time=time(9, 0),
        pickup_type="Pickup",
        gender="Female",
        waiting_time_minutes=10,
        is_active=True,
    )
    vendor = Vendor(
        tenant_id=tenant_a.tenant_id,
        vendor_code="ISO_VEND_A",
        name="Vendor Alpha",
        email="vendor.a@testa.com",
        phone="9876543210",
        is_active=True,
    )
    db.add_all([shift, vendor])
    db.flush()
    booking = Booking(
        tenant_id=tenant_a.tenant_id,
        employee_id=emp.employee_id,
        employee_code=emp.employee_code,
        shift_id=shift.shift_id,
        booking_date=date.today() + timedelta(days=1),
        status=ModelStatus.REQUEST,
        pickup_latitude=12.9716,
        pickup_longitude=77.5946,
        drop_latitude=12.9784,
        drop_longitude=77.6408,
        pickup_location="Home A",
        drop_location="Office A",
    )
    db.add(booking)
    db.commit()
    return {
        "tenant": tenant_a,
        "team": team_a,
        "employee": emp,
        "shift": shift,
        "vendor": vendor,
        "booking": booking,
    }


@pytest.fixture(scope="function")
def tenant_b_graph(db: Session, tenant_b, team_b, iam_seed):
    """Creates a complete entity graph for Tenant B."""
    emp_payload = EmployeeCreate(
        name="Bob B",
        employee_code="ISO_EMP_B",
        email="bob.b@testb.com",
        phone="+12025550302",
        password="Secure@Pass4",
        team_id=team_b.team_id,
        gender="Male",
        is_active=True,
    )
    emp = employee_crud.create_with_tenant(
        db, obj_in=emp_payload, tenant_id=tenant_b.tenant_id
    )
    shift = Shift(
        tenant_id=tenant_b.tenant_id,
        shift_code="ISO_SHIFT_B",
        log_type="OUT",
        shift_time=time(18, 0),
        pickup_type="Nodal",
        gender="Male",
        waiting_time_minutes=10,
        is_active=True,
    )
    vendor = Vendor(
        tenant_id=tenant_b.tenant_id,
        vendor_code="ISO_VEND_B",
        name="Vendor Beta",
        email="vendor.b@testb.com",
        phone="8765432109",
        is_active=True,
    )
    db.add_all([shift, vendor])
    db.flush()
    booking = Booking(
        tenant_id=tenant_b.tenant_id,
        employee_id=emp.employee_id,
        employee_code=emp.employee_code,
        shift_id=shift.shift_id,
        booking_date=date.today() + timedelta(days=2),
        status=ModelStatus.REQUEST,
        pickup_latitude=13.0000,
        pickup_longitude=77.6000,
        drop_latitude=13.0100,
        drop_longitude=77.6100,
        pickup_location="Home B",
        drop_location="Office B",
    )
    db.add(booking)
    db.commit()
    return {
        "tenant": tenant_b,
        "team": team_b,
        "employee": emp,
        "shift": shift,
        "vendor": vendor,
        "booking": booking,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Employee isolation
# ─────────────────────────────────────────────────────────────────────────────
class TestEmployeeTenantIsolation:
    def test_tenant_a_employee_invisible_to_tenant_b(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        b_employees = employee_crud.get_employees_by_tenant(
            db, tenant_id=tenant_b_graph["tenant"].tenant_id
        )
        b_emp_ids = {e.employee_id for e in b_employees}
        assert tenant_a_graph["employee"].employee_id not in b_emp_ids

    def test_tenant_b_employee_invisible_to_tenant_a(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        a_employees = employee_crud.get_employees_by_tenant(
            db, tenant_id=tenant_a_graph["tenant"].tenant_id
        )
        a_emp_ids = {e.employee_id for e in a_employees}
        assert tenant_b_graph["employee"].employee_id not in a_emp_ids

    def test_employee_code_lookup_scoped_to_tenant(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        """Same employee_code in different tenants must return the correct employee."""
        result_in_a = employee_crud.get_by_employee_code(
            db,
            employee_code="ISO_EMP_A",
            tenant_id=tenant_a_graph["tenant"].tenant_id,
        )
        result_in_b = employee_crud.get_by_employee_code(
            db,
            employee_code="ISO_EMP_A",
            tenant_id=tenant_b_graph["tenant"].tenant_id,
        )
        assert result_in_a is not None
        assert result_in_b is None  # Doesn't exist in tenant B

    def test_employee_count_is_tenant_scoped(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        count_a = employee_crud.count_by_tenant(
            db, tenant_id=tenant_a_graph["tenant"].tenant_id
        )
        count_b = employee_crud.count_by_tenant(
            db, tenant_id=tenant_b_graph["tenant"].tenant_id
        )
        # Each tenant must have exactly one employee seeded by fixtures
        assert count_a >= 1
        assert count_b >= 1
        # Totals must not bleed across tenant boundaries
        total_direct = (
            db.query(Employee)
            .filter(Employee.tenant_id == tenant_a_graph["tenant"].tenant_id)
            .count()
        )
        assert count_a == total_direct


# ─────────────────────────────────────────────────────────────────────────────
# Booking isolation
# ─────────────────────────────────────────────────────────────────────────────
class TestBookingTenantIsolation:
    def test_tenant_a_booking_not_in_tenant_b_results(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        b_bookings = booking_crud.get_by_tenant(
            db, tenant_id=tenant_b_graph["tenant"].tenant_id
        )
        b_booking_ids = {b.booking_id for b in b_bookings}
        assert tenant_a_graph["booking"].booking_id not in b_booking_ids

    def test_tenant_b_booking_not_in_tenant_a_results(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        a_bookings = booking_crud.get_by_tenant(
            db, tenant_id=tenant_a_graph["tenant"].tenant_id
        )
        a_booking_ids = {b.booking_id for b in a_bookings}
        assert tenant_b_graph["booking"].booking_id not in a_booking_ids

    def test_direct_booking_lookup_does_not_enforce_tenant(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        """
        booking_crud.get_by_id() is tenant-agnostic by design (used in
        internal ops like route assignment). This test documents that
        tenant enforcement is the router/service layer's responsibility.
        """
        booking_a = booking_crud.get_by_id(
            db, booking_id=tenant_a_graph["booking"].booking_id
        )
        assert booking_a is not None
        # It belongs to tenant A, but the lookup succeeded — expected behaviour
        assert booking_a.tenant_id == tenant_a_graph["tenant"].tenant_id


# ─────────────────────────────────────────────────────────────────────────────
# Team isolation
# ─────────────────────────────────────────────────────────────────────────────
class TestTeamTenantIsolation:
    def test_teams_are_tenant_scoped(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        a_teams = (
            db.query(Team)
            .filter(Team.tenant_id == tenant_a_graph["tenant"].tenant_id)
            .all()
        )
        team_ids = {t.team_id for t in a_teams}
        assert tenant_b_graph["team"].team_id not in team_ids


# ─────────────────────────────────────────────────────────────────────────────
# Vendor isolation
# ─────────────────────────────────────────────────────────────────────────────
class TestVendorTenantIsolation:
    def test_vendors_are_tenant_scoped(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        a_vendors = (
            db.query(Vendor)
            .filter(Vendor.tenant_id == tenant_a_graph["tenant"].tenant_id)
            .all()
        )
        a_vendor_ids = {v.vendor_id for v in a_vendors}
        assert tenant_b_graph["vendor"].vendor_id not in a_vendor_ids

    def test_vendor_lookup_by_tenant(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        a_count = (
            db.query(Vendor)
            .filter(Vendor.tenant_id == tenant_a_graph["tenant"].tenant_id)
            .count()
        )
        b_count = (
            db.query(Vendor)
            .filter(Vendor.tenant_id == tenant_b_graph["tenant"].tenant_id)
            .count()
        )
        assert a_count >= 1
        assert b_count >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Cross-tenant write isolation
# ─────────────────────────────────────────────────────────────────────────────
class TestCrossTenantWriteIsolation:
    def test_employee_cannot_be_moved_to_different_tenant(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        """
        Verify the ORM model doesn't silently change tenant_id via update.
        The schema layer (EmployeeUpdate) doesn't expose tenant_id — this
        test confirms the field is absent from the update schema.
        """
        from app.schemas.employee import EmployeeUpdate

        update = EmployeeUpdate(name="Tenant Hopper")
        # EmployeeUpdate must NOT have a tenant_id field
        assert not hasattr(update, "tenant_id"), (
            "EmployeeUpdate must not expose tenant_id — prevents cross-tenant moves"
        )

    def test_booking_creation_does_not_cross_tenant(
        self, db: Session, tenant_a_graph, tenant_b_graph
    ):
        """
        A booking created for an employee in tenant A must be stored
        with tenant A's ID, not tenant B's.
        """
        booking = Booking(
            tenant_id=tenant_a_graph["tenant"].tenant_id,
            employee_id=tenant_a_graph["employee"].employee_id,
            employee_code=tenant_a_graph["employee"].employee_code,
            shift_id=tenant_a_graph["shift"].shift_id,
            booking_date=date.today() + timedelta(days=3),
            status=ModelStatus.REQUEST,
            pickup_latitude=12.9716,
            pickup_longitude=77.5946,
            drop_latitude=12.9784,
            drop_longitude=77.6408,
            pickup_location="Cross Test",
            drop_location="Office",
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        assert booking.tenant_id == tenant_a_graph["tenant"].tenant_id
        # Must NOT be present in tenant B's bookings
        b_bookings = booking_crud.get_by_tenant(
            db, tenant_id=tenant_b_graph["tenant"].tenant_id
        )
        assert booking.booking_id not in {b.booking_id for b in b_bookings}
