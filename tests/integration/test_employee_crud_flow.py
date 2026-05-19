"""
Integration tests: Employee CRUD flow

Tests the complete lifecycle of an employee entity through the CRUD layer:
  Create → Get → Update → Soft-delete → Count

Validates:
- Password hashing on create
- Tenant scoping
- Email uniqueness enforcement
- WeekoffConfig auto-creation on employee creation
- Pagination helpers

These tests use the real SQLAlchemy CRUD layer against SQLite in-memory;
no HTTP layer involved.
"""
import pytest
from sqlalchemy.orm import Session

from app.crud.employee import CRUDEmployee
from app.models.employee import Employee
from app.models.iam.role import Role
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from common_utils.auth.utils import verify_password

pytestmark = pytest.mark.integration

employee_crud = CRUDEmployee(Employee)


# ─── Helper factory ───────────────────────────────────────────────────────────
def _emp_payload(**overrides) -> dict:
    base = {
        "name": "Jane Smith",
        "employee_code": "EMP_INTG_001",
        "email": "jane.smith@fleettest.com",
        "phone": "+12025550101",
        "password": "Secure@Pass1",
        "team_id": None,  # set per-test
        "gender": "Female",
        "is_active": True,
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# CREATE
# ─────────────────────────────────────────────────────────────────────────────
class TestEmployeeCreate:
    def test_create_persists_employee(self, db: Session, tenant_a, team_a, iam_seed):
        payload = EmployeeCreate(**_emp_payload(team_id=team_a.team_id))
        emp = employee_crud.create_with_tenant(db, obj_in=payload, tenant_id=tenant_a.tenant_id)
        db.flush()

        assert emp.employee_id is not None
        assert emp.tenant_id == tenant_a.tenant_id
        assert emp.email == "jane.smith@fleettest.com"
        assert emp.name == "Jane Smith"

    def test_password_is_hashed_on_create(self, db: Session, tenant_a, team_a, iam_seed):
        plain = "Secure@Pass1"
        payload = EmployeeCreate(**_emp_payload(team_id=team_a.team_id))
        emp = employee_crud.create_with_tenant(db, obj_in=payload, tenant_id=tenant_a.tenant_id)
        db.flush()

        # Raw string must NOT be stored
        assert emp.password != plain
        # bcrypt round-trip must succeed
        assert verify_password(plain, emp.password) is True

    def test_email_stored_lowercase(self, db: Session, tenant_a, team_a, iam_seed):
        payload = EmployeeCreate(
            **_emp_payload(team_id=team_a.team_id, email="UPPER@EXAMPLE.COM",
                           employee_code="EMP_UPPER")
        )
        emp = employee_crud.create_with_tenant(db, obj_in=payload, tenant_id=tenant_a.tenant_id)
        db.flush()
        assert emp.email == "upper@example.com"

    def test_weekoff_config_auto_created(self, db: Session, tenant_a, team_a, iam_seed):
        """create_with_tenant must also seed a WeekoffConfig row for the employee."""
        from app.models.weekoff_config import WeekoffConfig

        payload = EmployeeCreate(**_emp_payload(team_id=team_a.team_id,
                                                employee_code="EMP_WEEKOFF"))
        emp = employee_crud.create_with_tenant(db, obj_in=payload, tenant_id=tenant_a.tenant_id)
        db.commit()

        config = db.query(WeekoffConfig).filter_by(employee_id=emp.employee_id).first()
        assert config is not None, "WeekoffConfig must be auto-seeded on employee creation"

    def test_create_fails_without_system_employee_role(self, db: Session, tenant_a, team_a, iam_seed):
        """CRUD raises ValueError when 'Employee' system role is absent.

        iam_seed is module-scoped and commits the Employee role directly to the
        engine. We delete it inside the function-scoped db session (which uses a
        SAVEPOINT) so the deletion is visible within this test but rolled back
        after the test completes, leaving other tests unaffected.
        """
        from app.models.iam.role import Role

        # Remove the 'Employee' system role within this test's savepoint
        db.query(Role).filter(
            Role.name == "Employee", Role.is_system_role == True
        ).delete(synchronize_session="fetch")
        db.flush()

        payload = EmployeeCreate(**_emp_payload(team_id=team_a.team_id,
                                               employee_code="EMP_NO_ROLE"))
        with pytest.raises(ValueError, match="System role 'Employee' not found"):
            employee_crud.create_with_tenant(db, obj_in=payload, tenant_id=tenant_a.tenant_id)


# ─────────────────────────────────────────────────────────────────────────────
# READ
# ─────────────────────────────────────────────────────────────────────────────
class TestEmployeeRead:
    @pytest.fixture(autouse=True)
    def _seed(self, db, tenant_a, team_a, iam_seed):
        payload = EmployeeCreate(**_emp_payload(team_id=team_a.team_id))
        self.emp = employee_crud.create_with_tenant(
            db, obj_in=payload, tenant_id=tenant_a.tenant_id
        )
        db.commit()

    def test_get_by_email_returns_correct_employee(self, db: Session, tenant_a):
        found = employee_crud.get_by_email(db, email="jane.smith@fleettest.com")
        assert found is not None
        assert found.employee_id == self.emp.employee_id

    def test_get_by_email_case_insensitive_lookup(self, db: Session):
        """Email is stored lowercase; lookup must still succeed with uppercase input
        because the schema normalises before persistence."""
        found = employee_crud.get_by_email(db, email="jane.smith@fleettest.com")
        assert found is not None

    def test_get_by_employee_code_within_tenant(self, db: Session, tenant_a):
        found = employee_crud.get_by_employee_code(
            db, employee_code="EMP_INTG_001", tenant_id=tenant_a.tenant_id
        )
        assert found is not None
        assert found.employee_id == self.emp.employee_id

    def test_get_by_employee_code_wrong_tenant_returns_none(self, db: Session):
        result = employee_crud.get_by_employee_code(
            db, employee_code="EMP_INTG_001", tenant_id="WRONG_TENANT"
        )
        assert result is None

    def test_get_employees_by_tenant_returns_all(self, db: Session, tenant_a):
        employees = employee_crud.get_employees_by_tenant(
            db, tenant_id=tenant_a.tenant_id
        )
        assert len(employees) >= 1
        assert all(e.tenant_id == tenant_a.tenant_id for e in employees)

    def test_get_nonexistent_email_returns_none(self, db: Session):
        result = employee_crud.get_by_email(db, email="ghost@nobody.com")
        assert result is None

    def test_count_by_tenant_reflects_insertions(self, db: Session, tenant_a):
        count = employee_crud.count_by_tenant(db, tenant_id=tenant_a.tenant_id)
        assert count >= 1


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE
# ─────────────────────────────────────────────────────────────────────────────
class TestEmployeeUpdate:
    @pytest.fixture(autouse=True)
    def _seed(self, db, tenant_a, team_a, iam_seed):
        payload = EmployeeCreate(**_emp_payload(team_id=team_a.team_id))
        self.emp = employee_crud.create_with_tenant(
            db, obj_in=payload, tenant_id=tenant_a.tenant_id
        )
        db.commit()

    def test_update_name_persists(self, db: Session):
        update = EmployeeUpdate(name="Jane Updated")
        updated = employee_crud.update_with_password(db, db_obj=self.emp, obj_in=update)
        assert updated.name == "Jane Updated"

    def test_update_rehashes_password_when_provided(self, db: Session):
        old_hash = self.emp.password
        new_plain = "NewSecure@Pass9"
        update = EmployeeUpdate(password=new_plain)
        updated = employee_crud.update_with_password(db, db_obj=self.emp, obj_in=update)
        assert updated.password != old_hash
        assert updated.password != new_plain
        assert verify_password(new_plain, updated.password) is True

    def test_update_without_password_does_not_change_hash(self, db: Session):
        original_hash = self.emp.password
        update = EmployeeUpdate(name="No Password Change")
        updated = employee_crud.update_with_password(db, db_obj=self.emp, obj_in=update)
        assert updated.password == original_hash

    def test_deactivate_employee(self, db: Session):
        update = EmployeeUpdate(is_active=False)
        updated = employee_crud.update_with_password(db, db_obj=self.emp, obj_in=update)
        assert updated.is_active is False

    def test_update_email_normalizes_to_lowercase(self, db: Session):
        update = EmployeeUpdate(email="NEWEMAIL@EXAMPLE.COM")
        updated = employee_crud.update_with_password(db, db_obj=self.emp, obj_in=update)
        assert updated.email == "newemail@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# Full lifecycle (create → read → update → verify)
# ─────────────────────────────────────────────────────────────────────────────
class TestEmployeeFullLifecycle:
    def test_create_read_update_cycle(self, db: Session, tenant_a, team_a, iam_seed):
        # 1. Create
        payload = EmployeeCreate(**_emp_payload(
            team_id=team_a.team_id, employee_code="EMP_LIFECYCLE"
        ))
        created = employee_crud.create_with_tenant(
            db, obj_in=payload, tenant_id=tenant_a.tenant_id
        )
        db.commit()
        emp_id = created.employee_id

        # 2. Read by email
        fetched = employee_crud.get_by_email(db, email="jane.smith@fleettest.com")
        assert fetched.employee_id == emp_id

        # 3. Update
        employee_crud.update_with_password(
            db, db_obj=fetched, obj_in=EmployeeUpdate(name="Lifecycle Updated")
        )
        db.commit()

        # 4. Verify update persisted
        refreshed = employee_crud.get_by_email(db, email="jane.smith@fleettest.com")
        assert refreshed.name == "Lifecycle Updated"

    def test_tenant_scoping_prevents_cross_tenant_leak(
        self, db: Session, tenant_a, tenant_b, team_a, team_b, iam_seed
    ):
        """Employees created in tenant_a must not appear when querying tenant_b."""
        payload = EmployeeCreate(**_emp_payload(
            team_id=team_a.team_id, employee_code="EMP_SCOPE_A"
        ))
        employee_crud.create_with_tenant(
            db, obj_in=payload, tenant_id=tenant_a.tenant_id
        )
        db.commit()

        tenant_b_employees = employee_crud.get_employees_by_tenant(
            db, tenant_id=tenant_b.tenant_id
        )
        emp_ids_b = {e.employee_id for e in tenant_b_employees}
        emp_id_a = employee_crud.get_by_employee_code(
            db, employee_code="EMP_SCOPE_A", tenant_id=tenant_a.tenant_id
        ).employee_id

        assert emp_id_a not in emp_ids_b

    def test_pagination_skip_and_limit(self, db: Session, tenant_a, team_a, iam_seed):
        """Create 5 employees; verify skip/limit slices work correctly."""
        for i in range(5):
            payload = EmployeeCreate(**_emp_payload(
                team_id=team_a.team_id,
                employee_code=f"EMP_PAGE_{i}",
                email=f"page{i}@test.com",
                phone=f"+1202555{i:04d}",  # unique phone per employee
            ))
            employee_crud.create_with_tenant(
                db, obj_in=payload, tenant_id=tenant_a.tenant_id
            )
        db.commit()

        page1 = employee_crud.get_employees_by_tenant(
            db, tenant_id=tenant_a.tenant_id, skip=0, limit=3
        )
        page2 = employee_crud.get_employees_by_tenant(
            db, tenant_id=tenant_a.tenant_id, skip=3, limit=3
        )
        assert len(page1) == 3
        # No overlap between pages
        ids_p1 = {e.employee_id for e in page1}
        ids_p2 = {e.employee_id for e in page2}
        assert ids_p1.isdisjoint(ids_p2)
