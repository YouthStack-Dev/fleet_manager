"""
Integration test conftest — SQLite in-memory database with module-scoped
session for faster integration test execution.

Design decisions:
- Module-scoped engine: tables created once per module → faster than per-test
- Function-scoped session with rollback: each test gets a clean slate WITHOUT
  recreating the schema (savepoint pattern)
- Re-uses models/CRUD directly; no HTTP layer
- All external services (Redis, Email, FCM) are disabled/mocked at env level
"""
import pytest
from datetime import date, time
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.models.iam.permission import Permission
from app.models.iam.policy import Policy
from app.models.iam.role import Role
from app.models.tenant import Tenant
from app.models.team import Team
from common_utils.auth.utils import hash_password

# ─── Engine (module-scoped — schema created once) ─────────────────────────────
@pytest.fixture(scope="module")
def integration_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ─── Session (function-scoped — each test rolls back on teardown) ──────────────
@pytest.fixture(scope="function")
def db(integration_engine):
    """
    Provides a DB session that wraps each test in a SAVEPOINT and rolls back
    after the test completes. This is significantly faster than recreating
    tables per test.
    """
    connection = integration_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = SessionLocal()

    # Nested SAVEPOINT — lets the test code call session.commit() freely;
    # the outer transaction still rolls back at teardown.
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ─── Shared IAM seed (module-scoped — seeded once per module) ─────────────────
@pytest.fixture(scope="module")
def iam_seed(integration_engine):
    """
    Seeds the minimum IAM objects required by all integration tests:
    - System roles: SystemAdmin, Employee, Driver
    - Core permissions: CRUD on employee, booking, route
    """
    SessionLocal = sessionmaker(bind=integration_engine, autoflush=False)
    seed_session = SessionLocal()

    try:
        # System roles
        roles = [
            Role(role_id=1, tenant_id=None, name="SystemAdmin",
                 description="System Administrator", is_system_role=True, is_active=True),
            Role(role_id=2, tenant_id=None, name="Driver",
                 description="System Driver Role", is_system_role=True, is_active=True),
            Role(role_id=3, tenant_id=None, name="Employee",
                 description="System Employee Role", is_system_role=True, is_active=True),
        ]
        for r in roles:
            seed_session.merge(r)

        # Core permissions
        perms = []
        pid = 1
        for module in ["employee", "booking", "route", "admin_tenant", "team", "vendor", "driver"]:
            for action in ["create", "read", "update", "delete"]:
                perms.append(
                    Permission(permission_id=pid, module=module, action=action,
                               description=f"{action} {module}")
                )
                pid += 1
        for p in perms:
            seed_session.merge(p)

        seed_session.commit()
        yield {"roles": roles, "permissions": perms}
    finally:
        seed_session.close()


# ─── Tenant fixtures ───────────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def tenant_a(db, iam_seed):
    tenant = Tenant(
        tenant_id="INTG_TENANT_A",
        name="Integration Tenant A",
        address="100 Test Ave, Bengaluru",
        latitude=12.9716,
        longitude=77.5946,
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    return tenant


@pytest.fixture(scope="function")
def tenant_b(db, iam_seed):
    tenant = Tenant(
        tenant_id="INTG_TENANT_B",
        name="Integration Tenant B",
        address="200 Test Ave, Bengaluru",
        latitude=12.9720,
        longitude=77.5950,
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    return tenant


@pytest.fixture(scope="function")
def team_a(db, tenant_a):
    team = Team(
        tenant_id=tenant_a.tenant_id,
        name="Engineering Team A",
        description="Main engineering team",
        is_active=True,
    )
    db.add(team)
    db.flush()
    return team


@pytest.fixture(scope="function")
def team_b(db, tenant_b):
    team = Team(
        tenant_id=tenant_b.tenant_id,
        name="Engineering Team B",
        description="Second tenant team",
        is_active=True,
    )
    db.add(team)
    db.flush()
    return team
