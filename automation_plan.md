# Fleet Manager — QA Automation Framework Plan

**Version:** 1.0  
**Author:** QA Automation Architecture Team  
**Stack:** FastAPI + SQLAlchemy + PostgreSQL + Redis + Firebase FCM + Twilio + SMTP  
**Test Stack:** pytest + httpx (async) + pytest-asyncio + fakeredis + Allure + pytest-xdist  

---

## 1. Framework Overview

### 1.1 Philosophy

This framework is built on three principles:
- **Shift left**: Catch defects as early as possible, as cheaply as possible.
- **Isolation**: Every test must be independent and leave no side effects.
- **Fidelity**: Tests should exercise code paths as close to production as possible; mocks are confined to external I/O (FCM, Twilio, SMTP) only.

### 1.2 Technology Stack

| Layer | Tool | Purpose |
|---|---|---|
| Test runner | `pytest 7.x` | Discovery, execution, fixtures |
| Async support | `pytest-asyncio` | `asyncio_mode = auto` |
| HTTP client | `httpx.AsyncClient` | Full async API testing |
| DB (unit/integration) | `SQLite + StaticPool` | Fast, isolated, in-process |
| DB (contract tests) | `PostgreSQL 15` via Docker | Catch PG-specific behaviors |
| Redis mock | `fakeredis[aioredis]` | Redis behavior without daemon |
| Parallel execution | `pytest-xdist` | `-n auto` worker isolation |
| Reporting | `allure-pytest` + `pytest-html` | Structured reports + artifacts |
| Coverage | `pytest-cov` | Line + branch coverage |
| Factories | Manual factory classes | Deterministic, readable data |
| Secrets | `pydantic-settings` + GitHub Secrets | Never hardcoded |
| Pre-commit hooks | `detect-secrets` | Block credential commits |

### 1.3 Test Pyramid

```
                    ┌──────────────┐
                    │   E2E / API  │  20%  (~40 tests)
                    │  tests/api/  │  Full HTTP round-trips, auth flows
                   /│              │\
                  / └──────────────┘ \
                 /  ┌──────────────┐  \
                /   │ Integration  │   \
               /    │ tests/integ/ │    \  50%  (~100 tests)
              /     │              │     \  DB + service layer, real SQLAlchemy
             /      └──────────────┘      \
            /────────────────────────────────\
           /         Unit tests/unit/         \  30%  (~60 tests)
          /    Pure logic, validators, utils    \
         /____________________________________________\
```

**Why 50% integration?** The application's critical risk surface is the interaction between the permission layer, multi-tenant isolation, and the database. Unit tests cannot catch this; E2E tests are too slow to enumerate all boundary cases. Integration tests at the service/repository layer are the sweet spot.

### 1.4 Environment Matrix

| Environment | DB | Redis | FCM/Twilio/SMTP | When |
|---|---|---|---|---|
| `local` | SQLite in-memory | fakeredis | mocked | Developer `pytest` run |
| `ci-smoke` | SQLite in-memory | fakeredis | mocked | Every push |
| `ci-integration` | PostgreSQL 15 (Docker) | Redis 7 (Docker) | mocked | Every PR to main/develop |
| `ci-security` | PostgreSQL 15 (Docker) | Redis 7 (Docker) | mocked | Every PR to main |
| `staging` | Real PG (staging RDS) | Real Redis | mocked/sandbox | Post-merge to main |

---

## 2. Directory Structure

```
fleet_manager/
├── tests/
│   │
│   ├── conftest.py                        # ROOT conftest: engine, session, app, client, all mocks
│   ├── pytest.ini                         # Markers, asyncio mode, xdist, addopts
│   │
│   ├── unit/                              # Pure logic — no DB, no HTTP
│   │   ├── conftest.py                    # Unit-specific fixtures (no DB needed)
│   │   ├── test_booking_validators.py     # Pydantic validators: booking_date, booking_dates, shift_id
│   │   ├── test_permission_checker.py     # PermissionChecker logic, check_tenant, role hierarchy
│   │   ├── test_otp_utils.py              # OTP generation uniqueness, expiry, format
│   │   ├── test_token_utils.py            # JWT create/decode, expiry, type claims (pre_auth vs access)
│   │   └── test_business_rules.py        # Cutoff logic, booking window rules, shift overlap
│   │
│   ├── integration/                       # Service + DB layer — SQLAlchemy + SQLite/PG
│   │   ├── conftest.py                    # Integration DB fixtures, real PermissionChecker, fakeredis
│   │   ├── test_auth_flows.py             # Login, OTP, token refresh, logout, session invalidation
│   │   ├── test_booking_crud.py           # Create/read/update/cancel bookings, status transitions
│   │   ├── test_route_lifecycle.py        # Route create → assign drivers → dispatch → complete
│   │   ├── test_driver_flow.py            # Driver login, location update, active session management
│   │   ├── test_alert_lifecycle.py        # Alert config, trigger conditions, delivery
│   │   ├── test_announcement_lifecycle.py # Draft → publish, recipient deduplication, notification delivery
│   │   ├── test_iam_hierarchy.py          # Role inheritance, permission grants, tenant scoping
│   │   ├── test_session_management.py     # Single-session enforcement, Redis TTL, multi-worker scenario
│   │   └── test_concurrent_bookings.py    # Race condition: simultaneous duplicate booking attempts
│   │
│   ├── api/                               # Full HTTP layer — httpx AsyncClient against FastAPI app
│   │   ├── conftest.py                    # AsyncClient fixtures, base URL, auth header helpers
│   │   ├── test_auth_api.py               # All auth endpoints, 5 personas, error codes
│   │   ├── test_booking_api.py            # Booking CRUD via HTTP, pagination, filters
│   │   ├── test_route_api.py              # Route management endpoints, grouping endpoints (auth check)
│   │   ├── test_driver_api.py             # Driver app endpoints, location, OTP
│   │   ├── test_alert_api.py              # Alert config and delivery endpoints
│   │   ├── test_announcement_api.py       # Announcement create, publish, notification
│   │   ├── test_iam_api.py                # IAM CRUD, role assignment, permission listing
│   │   ├── test_reports_api.py            # Report generation, export formats, pagination
│   │   └── test_security_api.py           # Cross-cutting: auth bypass, tenant isolation, header injection
│   │
│   ├── security/                          # Dedicated security test suite
│   │   ├── test_auth_bypass.py            # Unauthenticated access to protected endpoints
│   │   ├── test_token_manipulation.py     # Invalid JWT, expired, wrong type, tampered signature
│   │   ├── test_sqli_xss.py               # SQL injection payloads in query params and request bodies
│   │   └── test_rbac_enforcement.py       # Role X cannot access Role Y's resources
│   │
│   ├── performance/                       # Rate limiting + load tests
│   │   ├── test_rate_limiting.py          # Redis sorted-set rate limit: 5/10 req/min on auth endpoints
│   │   └── locustfile.py                  # Locust load test: booking creation, login, route listing
│   │
│   └── fixtures/                          # Shared helpers (not pytest fixtures — utility modules)
│       ├── factory.py                     # BookingFactory, RouteFactory, EmployeeFactory, etc.
│       ├── auth_helpers.py                # create_token(), get_auth_headers() for all 5 personas
│       └── mock_services.py              # FakeRedis wrapper, FCM/Twilio/SMTP mock classes
│
├── .env.test                              # Test environment variables (no real secrets)
├── .secrets.baseline                      # detect-secrets baseline for pre-commit
│
└── scripts/
    ├── seed_test_data.py                  # Populate staging DB with deterministic test data
    └── run_tests.sh                       # Convenience wrapper: smoke | integration | all | security
```

---

## 3. Fixtures Strategy

### 3.1 Root `conftest.py` — Database Fixtures

```python
# tests/conftest.py
import pytest
import asyncio
from typing import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport
from fakeredis import FakeRedis
from unittest.mock import AsyncMock, patch

from app.main import app
from app.database.base import Base
from app.database.session import get_db
from app.core.redis_client import get_redis


# ---------------------------------------------------------------------------
# Engine — shared for the entire test session (fast SQLite in-memory)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_engine():
    """
    Single SQLite in-memory engine for the session.
    StaticPool ensures the same in-memory DB is reused across connections.
    NOTE: For PostgreSQL-specific behavior tests, override this fixture
    in tests/integration/conftest.py with a real PG URL.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable FK enforcement in SQLite (disabled by default)
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def SessionLocal(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


# ---------------------------------------------------------------------------
# Per-test DB session — wraps each test in a transaction, rolls back after
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db(test_engine, SessionLocal) -> Generator[Session, None, None]:
    """
    Function-scoped DB session.
    Each test gets a clean state via SAVEPOINT + rollback.
    This is orders of magnitude faster than dropping/recreating tables.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    # SQLite nested transaction support via SAVEPOINT
    session.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# FastAPI app with DB and Redis overrides
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def fake_redis():
    """FakeRedis instance — behaves like real Redis, in-process."""
    client = FakeRedis(decode_responses=True)
    yield client
    client.flushall()


@pytest.fixture(scope="function")
def override_dependencies(db, fake_redis):
    """
    Override FastAPI's get_db and get_redis with test fixtures.
    Restores originals after each test.
    """
    def _get_test_db():
        yield db

    def _get_test_redis():
        return fake_redis

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def client(override_dependencies) -> AsyncClient:
    """
    httpx AsyncClient backed by the FastAPI ASGI app.
    Uses dependency overrides so all requests hit the test DB and fake Redis.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as ac:
        yield ac
```

### 3.2 Auth Fixtures — All 5 Personas

```python
# tests/conftest.py (continued)
import os
from datetime import datetime, timedelta, timezone
from jose import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "test-jwt-secret-do-not-use-in-prod")
JWT_ALGORITHM = "HS256"


def _make_token(
    subject: str,
    role: str,
    tenant_id: int,
    token_type: str = "access",
    extra_claims: dict = None,
    expires_minutes: int = 30,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "tenant_id": tenant_id,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture(scope="function")
def tenant(db):
    """Create a test tenant and return its record."""
    from app.models.tenant import Tenant
    t = Tenant(name="qa_test_tenant", subdomain="qa-test", is_active=True)
    db.add(t)
    db.flush()
    return t


@pytest.fixture(scope="function")
def admin_user(db, tenant):
    from app.models.employee import Employee
    from app.core.security import get_password_hash
    emp = Employee(
        email="qa_admin@test.internal",
        hashed_password=get_password_hash("Test@1234!"),
        tenant_id=tenant.id,
        role="admin",
        is_active=True,
    )
    db.add(emp)
    db.flush()
    return emp


@pytest.fixture(scope="function")
def admin_token(admin_user, tenant) -> str:
    return _make_token(
        subject=str(admin_user.id),
        role="admin",
        tenant_id=tenant.id,
        extra_claims={"email": admin_user.email},
    )


@pytest.fixture(scope="function")
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="function")
def employee_user(db, tenant):
    from app.models.employee import Employee
    from app.core.security import get_password_hash
    emp = Employee(
        email="qa_employee@test.internal",
        hashed_password=get_password_hash("Test@1234!"),
        tenant_id=tenant.id,
        role="employee",
        is_active=True,
    )
    db.add(emp)
    db.flush()
    return emp


@pytest.fixture(scope="function")
def employee_token(employee_user, tenant) -> str:
    return _make_token(
        subject=str(employee_user.id),
        role="employee",
        tenant_id=tenant.id,
        extra_claims={"email": employee_user.email},
    )


@pytest.fixture(scope="function")
def employee_headers(employee_token) -> dict:
    return {"Authorization": f"Bearer {employee_token}"}


@pytest.fixture(scope="function")
def vendor_user(db, tenant):
    from app.models.vendor import Vendor
    v = Vendor(
        email="qa_vendor@test.internal",
        tenant_id=tenant.id,
        is_active=True,
    )
    db.add(v)
    db.flush()
    return v


@pytest.fixture(scope="function")
def vendor_token(vendor_user, tenant) -> str:
    return _make_token(
        subject=str(vendor_user.id),
        role="vendor",
        tenant_id=tenant.id,
    )


@pytest.fixture(scope="function")
def vendor_headers(vendor_token) -> dict:
    return {"Authorization": f"Bearer {vendor_token}"}


@pytest.fixture(scope="function")
def driver_user(db, tenant, vendor_user):
    from app.models.driver import Driver
    from app.core.security import get_password_hash
    d = Driver(
        phone="+919999000001",
        hashed_password=get_password_hash("Test@1234!"),
        tenant_id=tenant.id,
        vendor_id=vendor_user.id,
        is_active=True,
    )
    db.add(d)
    db.flush()
    return d


@pytest.fixture(scope="function")
def driver_token(driver_user, tenant) -> str:
    return _make_token(
        subject=str(driver_user.id),
        role="driver",
        tenant_id=tenant.id,
        extra_claims={"phone": driver_user.phone},
    )


@pytest.fixture(scope="function")
def driver_headers(driver_token) -> dict:
    return {"Authorization": f"Bearer {driver_token}"}


@pytest.fixture(scope="function")
def escort_user(db, tenant, vendor_user):
    from app.models.escort import Escort
    e = Escort(
        phone="+919999000002",
        tenant_id=tenant.id,
        vendor_id=vendor_user.id,
        is_active=True,
    )
    db.add(e)
    db.flush()
    return e


@pytest.fixture(scope="function")
def escort_token(escort_user, tenant) -> str:
    return _make_token(
        subject=str(escort_user.id),
        role="escort",
        tenant_id=tenant.id,
    )


@pytest.fixture(scope="function")
def escort_headers(escort_token) -> dict:
    return {"Authorization": f"Bearer {escort_token}"}
```

### 3.3 Test Data Factories

```python
# tests/fixtures/factory.py
"""
Manual factory classes for deterministic, readable test data.
Each factory returns the created ORM instance after flush (id is available).
Use db.flush() — not db.commit() — to keep tests inside the rollback boundary.
"""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session


class TenantFactory:
    @staticmethod
    def create(db: Session, name: str = "qa_factory_tenant", **kwargs):
        from app.models.tenant import Tenant
        t = Tenant(name=name, subdomain=name.lower().replace(" ", "-"), is_active=True, **kwargs)
        db.add(t)
        db.flush()
        return t


class EmployeeFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        db: Session,
        tenant_id: int,
        role: str = "employee",
        email: Optional[str] = None,
        **kwargs,
    ):
        from app.models.employee import Employee
        from app.core.security import get_password_hash
        cls._counter += 1
        emp = Employee(
            email=email or f"qa_emp_{cls._counter}@test.internal",
            hashed_password=get_password_hash("Test@1234!"),
            tenant_id=tenant_id,
            role=role,
            is_active=True,
            **kwargs,
        )
        db.add(emp)
        db.flush()
        return emp


class ShiftFactory:
    @staticmethod
    def create(db: Session, tenant_id: int, name: str = "Morning", **kwargs):
        from app.models.shift import Shift
        s = Shift(
            name=name,
            tenant_id=tenant_id,
            start_time="09:00:00",
            end_time="18:00:00",
            **kwargs,
        )
        db.add(s)
        db.flush()
        return s


class RouteFactory:
    _counter = 0

    @classmethod
    def create(cls, db: Session, tenant_id: int, **kwargs):
        from app.models.route import Route
        cls._counter += 1
        r = Route(
            name=f"qa_route_{cls._counter}",
            tenant_id=tenant_id,
            is_active=True,
            **kwargs,
        )
        db.add(r)
        db.flush()
        return r


class BookingFactory:
    @staticmethod
    def create(
        db: Session,
        employee_id: int,
        shift_id: int,
        tenant_id: int,
        booking_date: Optional[date] = None,
        **kwargs,
    ):
        from app.models.booking import Booking
        b = Booking(
            employee_id=employee_id,
            shift_id=shift_id,
            tenant_id=tenant_id,
            booking_date=booking_date or date.today() + timedelta(days=1),
            status="confirmed",
            **kwargs,
        )
        db.add(b)
        db.flush()
        return b


class VehicleFactory:
    _counter = 0

    @classmethod
    def create(cls, db: Session, tenant_id: int, vendor_id: int, **kwargs):
        from app.models.vehicle import Vehicle
        cls._counter += 1
        v = Vehicle(
            registration_number=f"QA{cls._counter:04d}",
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            is_active=True,
            **kwargs,
        )
        db.add(v)
        db.flush()
        return v


class AnnouncementFactory:
    @staticmethod
    def create(db: Session, tenant_id: int, created_by: int, **kwargs):
        from app.models.announcement import Announcement
        a = Announcement(
            title="QA Test Announcement",
            body="This is a test announcement created by QA.",
            tenant_id=tenant_id,
            created_by=created_by,
            status="draft",
            **kwargs,
        )
        db.add(a)
        db.flush()
        return a


class DriverFactory:
    _counter = 0

    @classmethod
    def create(cls, db: Session, tenant_id: int, vendor_id: int, **kwargs):
        from app.models.driver import Driver
        from app.core.security import get_password_hash
        cls._counter += 1
        d = Driver(
            phone=f"+9190000{cls._counter:05d}",
            hashed_password=get_password_hash("Test@1234!"),
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            is_active=True,
            **kwargs,
        )
        db.add(d)
        db.flush()
        return d
```

### 3.4 Service Mocks

```python
# tests/fixtures/mock_services.py
"""
Centralized mock definitions for all external services.
Import these into conftest.py or use as pytest fixtures directly.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fakeredis import FakeRedis


@pytest.fixture(autouse=True)
def mock_fcm(mocker):
    """
    Mock Firebase Cloud Messaging — blocks all real outbound push notifications.
    Tests that need to verify FCM was called should assert on mock_fcm.call_args.
    """
    return mocker.patch(
        "app.services.fcm_service.send_push_notification",
        new_callable=AsyncMock,
        return_value={"success": 1, "failure": 0},
    )


@pytest.fixture(autouse=True)
def mock_fcm_batch(mocker):
    return mocker.patch(
        "app.services.fcm_service.send_batch_push_notification",
        new_callable=AsyncMock,
        return_value={"success": 10, "failure": 0},
    )


@pytest.fixture(autouse=True)
def mock_twilio(mocker):
    """Mock Twilio SMS — no real SMS sent during tests."""
    mock = mocker.patch(
        "app.services.sms_service.send_sms",
        new_callable=AsyncMock,
        return_value=MagicMock(sid="SMTEST000000000000000000000000000"),
    )
    return mock


@pytest.fixture(autouse=True)
def mock_email(mocker):
    """Mock SMTP email sending."""
    return mocker.patch(
        "app.core.email_service.send_email",
        new_callable=AsyncMock,
        return_value=True,
    )


@pytest.fixture(autouse=True)
def mock_firebase_init(mocker):
    """Prevent firebase_admin.initialize_app() from running during tests."""
    mocker.patch("firebase_admin.initialize_app", return_value=None)
    mocker.patch("firebase_admin.credentials.Certificate", return_value=None)


class FakeRedisWithTracking(FakeRedis):
    """
    FakeRedis subclass that tracks all operations for assertion in tests.
    Usage: redis.get_calls, redis.set_calls, etc.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tracked_operations = []

    def set(self, name, value, *args, **kwargs):
        self._tracked_operations.append(("SET", name, value))
        return super().set(name, value, *args, **kwargs)

    def delete(self, *names):
        for name in names:
            self._tracked_operations.append(("DEL", name))
        return super().delete(*names)

    def get_operations(self, op_type=None):
        if op_type:
            return [op for op in self._tracked_operations if op[0] == op_type]
        return self._tracked_operations
```

---

## 4. Test Data Strategy

### 4.1 Static vs Dynamic

| Approach | When to Use | Example |
|---|---|---|
| **Static fixture** (conftest) | Shared setup needed by many tests | `tenant`, `admin_user`, `shift` |
| **Dynamic factory** (in-test) | Test-specific, unique data needed | `BookingFactory.create(db, ...)` in each test body |
| **Parameterized** | Boundary/edge case sweep | `@pytest.mark.parametrize` on booking_date values |
| **Bulk seeding** | Performance / load tests | `scripts/seed_test_data.py` |

### 4.2 Test Isolation via Transaction Rollback

Every test uses the function-scoped `db` fixture which wraps execution in a nested transaction:

```
Test starts
  → BEGIN SAVEPOINT sp_test_N
    → Test body runs (INSERT, UPDATE, SELECT)
  → ROLLBACK TO SAVEPOINT sp_test_N
Test ends — DB is in exact same state as before
```

This is **60–80% faster** than `Base.metadata.drop_all()` + `create_all()` between tests and is essential for the parallel execution strategy.

### 4.3 Parameterized Boundary Cases

```python
# tests/unit/test_booking_validators.py
import pytest
from datetime import date, timedelta

PAST_DATES = [
    date.today() - timedelta(days=1),
    date.today() - timedelta(days=30),
    date(2020, 1, 1),
]

VALID_FUTURE_DATES = [
    date.today() + timedelta(days=1),
    date.today() + timedelta(days=30),
]

@pytest.mark.parametrize("booking_date", PAST_DATES)
def test_booking_validator_rejects_past_dates(booking_date):
    """booking_date validator must reject past dates — currently a no-op bug (DEFECT-010)."""
    from app.schemas.booking import BookingCreateSchema
    with pytest.raises(ValueError, match="booking date cannot be in the past"):
        BookingCreateSchema(
            employee_id=1,
            shift_id=1,
            booking_dates=[booking_date],  # note: list field
        )


@pytest.mark.parametrize("booking_date", VALID_FUTURE_DATES)
def test_booking_validator_accepts_future_dates(booking_date):
    from app.schemas.booking import BookingCreateSchema
    schema = BookingCreateSchema(
        employee_id=1,
        shift_id=1,
        booking_dates=[booking_date],
    )
    assert booking_date in schema.booking_dates
```

### 4.4 Sensitive Data Handling

- **Never hardcode** passwords, JWT secrets, or API keys in test files.
- Use environment variable defaults: `os.environ.get("JWT_SECRET", "test-only-secret")`
- `.env.test` is committed **without real values** — template only.
- Real secrets injected via GitHub Secrets → environment variables in CI.
- `detect-secrets` pre-commit hook blocks accidental credential commits.

### 4.5 Naming Conventions

```
# Users / emails created in tests
qa_admin@test.internal
qa_employee_{n}@test.internal
qa_vendor@test.internal

# Tenant names
qa_test_tenant
qa_factory_tenant_{n}

# Route names / booking identifiers
qa_route_{n}
qa_booking_{uuid}

# Test phone numbers (non-real range)
+919900000001 through +919900009999
```

---

## 5. Parallel Execution

### 5.1 pytest.ini Configuration

```ini
# tests/pytest.ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

markers =
    smoke: Fast critical path tests — run on every push
    regression: Full regression suite
    unit: No DB, no HTTP — pure logic
    integration: DB + service layer
    security: Auth bypass, RBAC, injection tests
    performance: Rate limiting and load tests
    slow: Tests taking > 5s — excluded from fast runs

addopts =
    -v
    --tb=short
    --strict-markers
    --cov=app
    --cov-report=term-missing
    --cov-report=html:reports/coverage
    --html=reports/report.html
    --self-contained-html
    -p no:warnings

# Parallel execution (uncomment for CI, keep commented for local debugging)
# addopts = -n auto --dist=loadgroup
```

### 5.2 Worker Isolation Strategy

```python
# tests/conftest.py — parallel-safe DB setup
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool, NullPool

def get_test_db_url():
    """
    In parallel mode (pytest-xdist), each worker gets its own DB.
    Worker IDs are: gw0, gw1, gw2, ...
    For SQLite: each worker gets a named file (not :memory:) to avoid sharing.
    For PostgreSQL: each worker gets a separate schema.
    """
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
    db_url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

    if "sqlite" in db_url:
        if worker_id == "main":
            return "sqlite:///:memory:"
        # Named file per worker for xdist isolation
        return f"sqlite:///./test_{worker_id}.db"

    if "postgresql" in db_url:
        # Each worker uses a separate schema: test_gw0, test_gw1, etc.
        schema = f"test_{worker_id}"
        return db_url  # Schema set via search_path below

    return db_url
```

**loadgroup strategy** — group tests by module so DB-heavy tests run on dedicated workers:

```python
# Example: mark tests to run on the same xdist worker
# tests/integration/test_booking_crud.py

pytestmark = pytest.mark.xdist_group("booking")  # All booking tests on same worker

# tests/integration/test_auth_flows.py
pytestmark = pytest.mark.xdist_group("auth")
```

### 5.3 Redis Mock Isolation in Parallel

Each worker gets its own `FakeRedis` instance because fakeredis is in-process:

```python
@pytest.fixture(scope="function")
def fake_redis():
    """
    FakeRedis is always in-process — no sharing between xdist workers.
    Each function-scoped fixture call creates an isolated instance.
    flushall() on teardown prevents state leakage within the same worker.
    """
    client = FakeRedis(decode_responses=True)
    yield client
    client.flushall()
```

---

## 6. CI/CD Integration

### 6.1 Full GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.11"
  JWT_SECRET: ${{ secrets.TEST_JWT_SECRET }}
  INTROSPECT_SECRET: ${{ secrets.TEST_INTROSPECT_SECRET }}

jobs:
  # ─────────────────────────────────────────────────────────────
  # JOB 1: Smoke Tests — run on EVERY push, fast feedback
  # ─────────────────────────────────────────────────────────────
  smoke-tests:
    name: Smoke Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ env.PYTHON_VERSION }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest-html allure-pytest fakeredis pytest-mock pytest-cov

      - name: Run smoke tests
        run: |
          pytest tests/ -m smoke \
            --tb=short \
            -v \
            --junitxml=reports/smoke-results.xml \
            --html=reports/smoke-report.html \
            --self-contained-html
        env:
          DATABASE_URL: sqlite:///:memory:
          REDIS_URL: ""
          JWT_SECRET: ${{ env.JWT_SECRET }}
          JWT_ALGORITHM: HS256
          ACCESS_TOKEN_EXPIRE_MINUTES: 30
          REFRESH_TOKEN_EXPIRE_DAYS: 7
          FCM_CREDENTIALS_PATH: ""
          TWILIO_ACCOUNT_SID: ""
          TWILIO_AUTH_TOKEN: ""
          SMTP_HOST: ""
          SMTP_PORT: "587"
          RUN_MIGRATIONS_ON_STARTUP: "false"

      - name: Upload smoke test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: smoke-test-report
          path: reports/smoke-report.html
          retention-days: 7

  # ─────────────────────────────────────────────────────────────
  # JOB 2: Integration Tests — PostgreSQL + Redis services
  # Only on PR to main/develop
  # ─────────────────────────────────────────────────────────────
  integration-tests:
    name: Integration Tests (PG + Redis)
    needs: smoke-tests
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'

    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: fleet_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass_ci
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest-html allure-pytest fakeredis pytest-mock pytest-cov pytest-xdist

      - name: Wait for PostgreSQL
        run: |
          until pg_isready -h localhost -p 5432 -U test_user; do
            echo "Waiting for postgres..."
            sleep 2
          done

      - name: Run database migrations
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql://test_user:test_pass_ci@localhost:5432/fleet_test

      - name: Run integration tests
        run: |
          pytest tests/integration/ \
            -m integration \
            --tb=short \
            -v \
            -n auto \
            --dist=loadgroup \
            --junitxml=reports/integration-results.xml \
            --alluredir=reports/allure-results
        env:
          DATABASE_URL: postgresql://test_user:test_pass_ci@localhost:5432/fleet_test
          REDIS_URL: redis://localhost:6379/0
          JWT_SECRET: ${{ env.JWT_SECRET }}
          JWT_ALGORITHM: HS256
          ACCESS_TOKEN_EXPIRE_MINUTES: 30
          REFRESH_TOKEN_EXPIRE_DAYS: 7
          RUN_MIGRATIONS_ON_STARTUP: "false"
          FCM_CREDENTIALS_PATH: ""
          TWILIO_ACCOUNT_SID: ""
          TWILIO_AUTH_TOKEN: ""
          SMTP_HOST: ""

      - name: Generate Allure report
        if: always()
        run: |
          npm install -g allure-commandline
          allure generate reports/allure-results --clean -o reports/allure-report

      - name: Upload Allure report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: allure-integration-report
          path: reports/allure-report
          retention-days: 14

      - name: Upload JUnit results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: integration-junit
          path: reports/integration-results.xml

  # ─────────────────────────────────────────────────────────────
  # JOB 3: Security Tests — dedicated job, blocks merge on failure
  # ─────────────────────────────────────────────────────────────
  security-tests:
    name: Security Tests
    needs: smoke-tests
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'

    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: fleet_security_test
          POSTGRES_USER: sec_test
          POSTGRES_PASSWORD: sec_pass_ci
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest-html allure-pytest fakeredis pytest-mock

      - name: Run migrations
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql://sec_test:sec_pass_ci@localhost:5432/fleet_security_test

      - name: Run security tests
        run: |
          pytest tests/security/ \
            -m security \
            --tb=long \
            -v \
            --junitxml=reports/security-results.xml \
            --html=reports/security-report.html \
            --self-contained-html
        env:
          DATABASE_URL: postgresql://sec_test:sec_pass_ci@localhost:5432/fleet_security_test
          JWT_SECRET: ${{ env.JWT_SECRET }}
          RUN_MIGRATIONS_ON_STARTUP: "false"

      - name: Upload security report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: security-test-report
          path: reports/security-report.html

  # ─────────────────────────────────────────────────────────────
  # JOB 4: Publish Allure to GitHub Pages (main branch only)
  # ─────────────────────────────────────────────────────────────
  publish-allure:
    name: Publish Allure Report
    needs: integration-tests
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    permissions:
      contents: write
      pages: write

    steps:
      - uses: actions/checkout@v4

      - name: Download Allure report artifact
        uses: actions/download-artifact@v4
        with:
          name: allure-integration-report
          path: allure-report

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: allure-report
          destination_dir: test-reports/${{ github.run_number }}

  # ─────────────────────────────────────────────────────────────
  # JOB 5: Slack Notification on failure
  # ─────────────────────────────────────────────────────────────
  notify-on-failure:
    name: Slack Failure Notification
    needs: [smoke-tests, integration-tests, security-tests]
    runs-on: ubuntu-latest
    if: failure()

    steps:
      - name: Notify Slack
        uses: slackapi/slack-github-action@v1.26.0
        with:
          payload: |
            {
              "text": ":red_circle: *Fleet Manager Tests FAILED*",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": ":red_circle: *Test suite failed on `${{ github.ref_name }}`*\n*PR:* ${{ github.event.pull_request.html_url || github.server_url }}\n*Commit:* ${{ github.sha }}\n*Author:* ${{ github.actor }}\n*Run:* ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
                  }
                }
              ]
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          SLACK_WEBHOOK_TYPE: INCOMING_WEBHOOK
```

---

## 7. Reporting (Allure + HTML)

### 7.1 Allure Integration in Test Code

```python
# tests/api/test_auth_api.py
import allure
import pytest
from httpx import AsyncClient


@allure.feature("Authentication")
@allure.story("Employee Login")
class TestEmployeeLogin:

    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("Successful employee login returns 200 with access token")
    @pytest.mark.smoke
    async def test_employee_login_success(self, client: AsyncClient, employee_user):
        with allure.step("Prepare valid login credentials"):
            payload = {
                "email": employee_user.email,
                "password": "Test@1234!",
            }

        with allure.step("POST /api/v1/auth/employee/login"):
            response = await client.post("/api/v1/auth/employee/login", json=payload)

        with allure.step("Assert 200 OK and token structure"):
            assert response.status_code == 200
            body = response.json()
            assert "access_token" in body
            assert "refresh_token" in body
            assert body["token_type"] == "bearer"

        allure.attach(
            str(body),
            name="Response Body",
            attachment_type=allure.attachment_type.JSON,
        )

    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("Invalid password returns 401")
    @pytest.mark.smoke
    async def test_employee_login_wrong_password(self, client: AsyncClient, employee_user):
        with allure.step("POST with wrong password"):
            response = await client.post(
                "/api/v1/auth/employee/login",
                json={"email": employee_user.email, "password": "WrongPass!"},
            )

        with allure.step("Assert 401 Unauthorized"):
            assert response.status_code == 401

    @allure.severity(allure.severity_level.HIGH)
    @allure.title("Rate limiting blocks > 5 login attempts per minute")
    @pytest.mark.security
    async def test_login_rate_limit_enforced(self, client: AsyncClient, employee_user):
        with allure.step("Send 6 rapid login attempts"):
            responses = []
            for _ in range(6):
                r = await client.post(
                    "/api/v1/auth/employee/login",
                    json={"email": employee_user.email, "password": "WrongPass!"},
                )
                responses.append(r)

        with allure.step("Assert 6th attempt is rate-limited (429)"):
            assert any(r.status_code == 429 for r in responses), (
                "Rate limiting not enforced after 5 failed attempts"
            )
```

### 7.2 Allure Configuration

```ini
# pytest.ini additions for Allure
[pytest]
addopts =
    --alluredir=reports/allure-results
    --clean-alluredir
```

**Report generation and serving:**
```bash
# Generate HTML report from results
allure generate reports/allure-results --clean -o reports/allure-report

# Serve locally
allure serve reports/allure-results

# Open static report
allure open reports/allure-report
```

### 7.3 Allure Categories (categorize failures)

```json
// tests/allure-categories.json
[
  {
    "name": "Auth Failures",
    "matchedStatuses": ["failed"],
    "traceRegex": ".*AuthenticationError.*"
  },
  {
    "name": "DB Constraint Violations",
    "matchedStatuses": ["failed"],
    "traceRegex": ".*IntegrityError.*"
  },
  {
    "name": "Permission Denied",
    "matchedStatuses": ["failed"],
    "traceRegex": ".*403.*"
  }
]
```

---

## 8. Environment Configuration

### 8.1 `.env.test` Template

```dotenv
# .env.test — TEMPLATE ONLY — no real secrets
# Copy to .env.test.local and fill in values for local dev
# CI injects these via GitHub Secrets

# ── Database ──────────────────────────────────────────────────
DATABASE_URL=sqlite:///:memory:
# For integration tests against real PG:
# DATABASE_URL=postgresql://test_user:test_pass@localhost:5432/fleet_test

# ── Redis ─────────────────────────────────────────────────────
REDIS_URL=
# For integration tests against real Redis:
# REDIS_URL=redis://localhost:6379/0

# ── JWT ───────────────────────────────────────────────────────
JWT_SECRET=test-jwt-secret-do-not-use-in-prod-replace-in-ci
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
INTROSPECT_SECRET=test-introspect-secret-do-not-use-in-prod

# ── Firebase FCM ──────────────────────────────────────────────
FCM_CREDENTIALS_PATH=
# Leave empty — FCM is mocked in all tests

# ── Twilio SMS ────────────────────────────────────────────────
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
# Leave empty — Twilio is mocked in all tests

# ── SMTP Email ────────────────────────────────────────────────
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=noreply@test.internal
# Leave empty — SMTP is mocked in all tests

# ── App Config ────────────────────────────────────────────────
RUN_MIGRATIONS_ON_STARTUP=false
ENVIRONMENT=test
DEBUG=false
LOG_LEVEL=WARNING

# ── OTP ───────────────────────────────────────────────────────
OTP_EXPIRY_SECONDS=300
OTP_LENGTH=6
```

### 8.2 Loading Config with pydantic-settings

```python
# app/core/test_config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class TestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.test",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "sqlite:///:memory:"
    redis_url: Optional[str] = None
    jwt_secret: str = "test-jwt-secret-do-not-use-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    run_migrations_on_startup: bool = False
    environment: str = "test"


test_settings = TestSettings()
```

---

## 9. Secrets Handling

### 9.1 Pre-commit Hook: detect-secrets

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: |
          (?x)^(
            .env.test|
            tests/fixtures/auth_helpers.py
          )$

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: detect-private-key
```

**Initialize baseline:**
```bash
detect-secrets scan --exclude-files '.env.test' > .secrets.baseline
```

### 9.2 GitHub Secrets Required

```
TEST_JWT_SECRET          → Random 64-char hex string, rotated quarterly
TEST_INTROSPECT_SECRET   → Random 32-char hex string
SLACK_WEBHOOK_URL        → CI failure notifications
# Add DB passwords if running real PG in CI
```

### 9.3 Secrets Rotation Policy

- `TEST_JWT_SECRET` and `TEST_INTROSPECT_SECRET`: rotate every 90 days.
- Never use production secrets in tests — maintain completely separate secret sets.
- Invalidate old test tokens by changing `JWT_SECRET` — all existing test JWTs immediately rejected.

---

## 10. Addressing Current Test Coverage Gaps

### Gap 1: PermissionChecker Always Mocked

**Problem:** `PermissionChecker` is patched out in all 33 existing tests. No test ever verifies that permission enforcement actually works. A role with no permissions can access any endpoint.

**Fix:**

```python
# tests/integration/test_iam_hierarchy.py
import pytest
import allure
from httpx import AsyncClient


@allure.feature("IAM")
@allure.story("RBAC Enforcement")
class TestRBACEnforcement:

    @pytest.mark.integration
    async def test_employee_cannot_access_admin_endpoint(
        self, client: AsyncClient, employee_headers: dict
    ):
        """
        Uses real PermissionChecker (NOT mocked).
        Employee role must not access admin-only endpoints.
        """
        response = await client.get(
            "/api/v1/admin/tenants",
            headers=employee_headers,
        )
        assert response.status_code == 403, (
            f"Employee accessed admin endpoint — got {response.status_code}"
        )

    @pytest.mark.integration
    async def test_vendor_cannot_create_booking(
        self, client: AsyncClient, vendor_headers: dict
    ):
        response = await client.post(
            "/api/v1/bookings/",
            json={"booking_dates": ["2099-01-01"], "shift_id": 1},
            headers=vendor_headers,
        )
        assert response.status_code in (403, 422)

    @pytest.mark.integration
    async def test_cross_tenant_access_blocked(
        self,
        client: AsyncClient,
        db,
        tenant,
    ):
        """
        Employee of tenant A must NOT see bookings of tenant B.
        Catches DEFECT-004 (check_tenant commented out).
        """
        from tests.fixtures.factory import TenantFactory, EmployeeFactory, BookingFactory, ShiftFactory
        import os
        from tests.conftest import _make_token

        # Create tenant B with its own employee and booking
        tenant_b = TenantFactory.create(db, name="qa_tenant_b")
        shift_b = ShiftFactory.create(db, tenant_id=tenant_b.id)
        emp_b = EmployeeFactory.create(db, tenant_id=tenant_b.id)
        booking_b = BookingFactory.create(
            db, employee_id=emp_b.id, shift_id=shift_b.id, tenant_id=tenant_b.id
        )

        # Tenant A employee token (tenant.id != tenant_b.id)
        token_a = _make_token(
            subject="99999",
            role="admin",
            tenant_id=tenant.id,
        )

        # Attempt to access tenant B's booking
        response = await client.get(
            f"/api/v1/bookings/{booking_b.id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert response.status_code in (403, 404), (
            "Cross-tenant data leakage: tenant A accessed tenant B booking"
        )
```

**Integration conftest override — disable the mock:**
```python
# tests/integration/conftest.py
# Do NOT import or apply mock_permission_checker fixture here.
# Integration tests use the real PermissionChecker.
```

### Gap 2: Rate Limiting Not Tested

**Problem:** Auth endpoints enforce 5–10 req/min via Redis sorted sets. Tests never verify this.

**Fix:**

```python
# tests/performance/test_rate_limiting.py
import pytest
import asyncio
from httpx import AsyncClient


@pytest.mark.performance
class TestRateLimiting:

    async def test_auth_endpoint_rate_limit_5_per_min(
        self, client: AsyncClient, fake_redis
    ):
        """
        Auth endpoints allow max 5 requests per minute per IP.
        The 6th request must return 429 Too Many Requests.
        """
        payload = {"email": "nonexistent@test.internal", "password": "wrong"}
        responses = []

        # Send 6 rapid requests
        for i in range(6):
            r = await client.post("/api/v1/auth/employee/login", json=payload)
            responses.append(r.status_code)

        assert 429 in responses, (
            f"Rate limiting not enforced. Status codes: {responses}"
        )
        # First 5 should be 401 (wrong credentials), not 429
        assert responses[:5].count(401) >= 4, (
            "Unexpected early rate limiting before 5th request"
        )

    async def test_rate_limit_resets_after_window(
        self, client: AsyncClient, fake_redis
    ):
        """After the rate limit window expires, requests should succeed again."""
        payload = {"email": "nonexistent@test.internal", "password": "wrong"}

        # Exhaust rate limit
        for _ in range(5):
            await client.post("/api/v1/auth/employee/login", json=payload)

        # Simulate window expiry by clearing Redis rate limit keys
        keys = fake_redis.keys("rate_limit:*")
        for key in keys:
            fake_redis.delete(key)

        # Next request should proceed (not 429)
        r = await client.post("/api/v1/auth/employee/login", json=payload)
        assert r.status_code != 429, "Rate limit not reset after window clear"
```

### Gap 3: Concurrent Booking Race Condition

**Problem:** Two concurrent `POST /bookings` for the same `(employee_id, booking_date, shift_id)` can both succeed because there is no DB UNIQUE constraint — only a SELECT-before-INSERT check.

**Fix:**

```python
# tests/integration/test_concurrent_bookings.py
import pytest
import asyncio
from httpx import AsyncClient
from tests.fixtures.factory import EmployeeFactory, ShiftFactory, BookingFactory


@pytest.mark.integration
class TestConcurrentBookings:

    async def test_concurrent_duplicate_booking_creates_only_one(
        self, client: AsyncClient, admin_headers: dict, db, tenant
    ):
        """
        Two simultaneous POST /bookings requests for the same
        (employee_id, booking_date, shift_id) must result in only 1 booking.
        This test WILL FAIL until DEFECT-005 (missing UNIQUE constraint) is fixed.
        """
        from datetime import date, timedelta

        emp = EmployeeFactory.create(db, tenant_id=tenant.id)
        shift = ShiftFactory.create(db, tenant_id=tenant.id)
        future_date = (date.today() + timedelta(days=2)).isoformat()

        booking_payload = {
            "employee_id": emp.id,
            "shift_id": shift.id,
            "booking_dates": [future_date],
        }

        # Fire two requests concurrently
        results = await asyncio.gather(
            client.post("/api/v1/bookings/", json=booking_payload, headers=admin_headers),
            client.post("/api/v1/bookings/", json=booking_payload, headers=admin_headers),
            return_exceptions=True,
        )

        status_codes = [
            r.status_code for r in results if not isinstance(r, Exception)
        ]

        # Exactly one should succeed (201), the other should fail (409 Conflict or 422)
        success_count = status_codes.count(201)
        assert success_count == 1, (
            f"Expected exactly 1 successful booking, got {success_count}. "
            f"Status codes: {status_codes}. "
            f"DEFECT-005: No UNIQUE constraint on (employee_id, booking_date, shift_id)"
        )

    async def test_concurrent_driver_login_creates_only_one_active_session(
        self, client: AsyncClient, driver_user, db
    ):
        """
        Two simultaneous driver logins must result in only one active session.
        Catches DEFECT-006: no UNIQUE constraint on driver_sessions(driver_id, is_active=True).
        """
        login_payload = {
            "phone": driver_user.phone,
            "password": "Test@1234!",
            "device_token": "test-device-fcm-token",
        }

        results = await asyncio.gather(
            client.post("/api/v1/auth/driver/login", json=login_payload),
            client.post("/api/v1/auth/driver/login", json=login_payload),
            return_exceptions=True,
        )

        # Query active sessions for this driver
        from app.models.driver_session import DriverSession
        active_sessions = (
            db.query(DriverSession)
            .filter(
                DriverSession.driver_id == driver_user.id,
                DriverSession.is_active == True,
            )
            .all()
        )

        assert len(active_sessions) == 1, (
            f"Expected 1 active driver session, found {len(active_sessions)}. "
            f"DEFECT-006: Race condition in driver session creation."
        )
```

### Gap 4: API Drift Detection

**Problem:** Test files reference `/api/v1/auth/driver/login` and `/driver/new/login` which no longer exist. CI passes these tests incorrectly (the app returns 404, tests may not assert the URL).

**Fix:**

```python
# tests/api/test_api_contract.py
"""
API Contract tests: verify all expected endpoints exist and return
non-404 responses (even 401/403 is acceptable — it means the route exists).
This file is the canary for API drift.
"""
import pytest
from httpx import AsyncClient

EXPECTED_ENDPOINTS = [
    # Auth
    ("POST", "/api/v1/auth/employee/login"),
    ("POST", "/api/v1/auth/admin/login"),
    ("POST", "/api/v1/auth/vendor/login"),
    ("POST", "/api/v1/auth/driver/login"),
    ("POST", "/api/v1/auth/escort/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/reset-password"),
    # Bookings
    ("GET",  "/api/v1/bookings/"),
    ("POST", "/api/v1/bookings/"),
    # Routes
    ("GET",  "/api/v1/routes/"),
    ("POST", "/api/v1/routes/"),
    # Announcements
    ("GET",  "/api/v1/announcements/"),
    ("POST", "/api/v1/announcements/"),
    # Push notifications
    ("POST", "/api/v1/push-notifications/send"),
    ("POST", "/api/v1/push-notifications/send-batch"),
    # Metrics
    ("GET",  "/metrics"),
]

REMOVED_ENDPOINTS = [
    # These must NOT exist — add here when endpoints are deleted
    ("POST", "/driver/new/login"),
]


@pytest.mark.smoke
class TestAPIContract:

    @pytest.mark.parametrize("method,path", EXPECTED_ENDPOINTS)
    async def test_endpoint_exists(self, client: AsyncClient, method: str, path: str):
        """
        Endpoint must return something other than 404/405.
        401/403 means the route exists but requires auth — acceptable.
        """
        r = await client.request(method, path, json={})
        assert r.status_code != 404, (
            f"ENDPOINT NOT FOUND: {method} {path} returned 404. "
            f"API drift detected — update tests or restore endpoint."
        )

    @pytest.mark.parametrize("method,path", REMOVED_ENDPOINTS)
    async def test_removed_endpoint_is_gone(self, client: AsyncClient, method: str, path: str):
        """Removed endpoints must return 404 — catches accidental restoration."""
        r = await client.request(method, path, json={})
        assert r.status_code == 404, (
            f"REMOVED ENDPOINT STILL EXISTS: {method} {path} returned {r.status_code}"
        )
```

### Gap 5: Redis Session Behavior

**Problem:** Redis session enforcement (single session per user, TTL, invalidation) is never tested because Redis is mocked as a no-op.

**Fix:**

```python
# tests/integration/test_session_management.py
import pytest
from fakeredis import FakeRedis
from httpx import AsyncClient


@pytest.mark.integration
class TestRedisSessionManagement:

    async def test_second_login_invalidates_first_session(
        self, client: AsyncClient, employee_user, fake_redis
    ):
        """
        Logging in a second time must invalidate the first session token.
        Verifies single-session enforcement via Redis.
        """
        credentials = {"email": employee_user.email, "password": "Test@1234!"}

        # First login
        r1 = await client.post("/api/v1/auth/employee/login", json=credentials)
        assert r1.status_code == 200
        token1 = r1.json()["access_token"]

        # Second login
        r2 = await client.post("/api/v1/auth/employee/login", json=credentials)
        assert r2.status_code == 200
        token2 = r2.json()["access_token"]

        # First token should now be rejected
        r_old = await client.get(
            "/api/v1/employees/me",
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert r_old.status_code == 401, (
            "First session token still valid after second login — "
            "single-session enforcement failed"
        )

        # Second token should be valid
        r_new = await client.get(
            "/api/v1/employees/me",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert r_new.status_code == 200

    async def test_logout_invalidates_session_in_redis(
        self, client: AsyncClient, employee_headers: dict, employee_user, fake_redis
    ):
        """After logout, session key must be deleted from Redis."""
        r = await client.post("/api/v1/auth/logout", headers=employee_headers)
        assert r.status_code == 200

        # Redis session key must not exist
        session_key = f"employee_session:{employee_user.id}"
        assert not fake_redis.exists(session_key), (
            f"Session key '{session_key}' still in Redis after logout"
        )

    async def test_session_ttl_is_set_on_login(
        self, client: AsyncClient, employee_user, fake_redis
    ):
        """Redis session key must have a TTL set on login."""
        credentials = {"email": employee_user.email, "password": "Test@1234!"}
        r = await client.post("/api/v1/auth/employee/login", json=credentials)
        assert r.status_code == 200

        session_key = f"employee_session:{employee_user.id}"
        ttl = fake_redis.ttl(session_key)
        assert ttl > 0, f"Session key has no TTL (ttl={ttl}) — will never expire"
        assert ttl <= 86400, f"Session TTL suspiciously large: {ttl}s"
```

---

## 11. Sample Test Implementations for Critical Defects

### 11.1 Password Reset Stub (DEFECT-001)

```python
# tests/api/test_auth_api.py
@pytest.mark.regression
async def test_password_reset_is_not_a_stub(client: AsyncClient, employee_user, mock_email):
    """
    POST /auth/reset-password must NOT return 200 without sending an email.
    Currently a stub — always returns 200 with fake message (DEFECT-001).
    """
    r = await client.post(
        "/api/v1/auth/reset-password",
        json={"email": employee_user.email},
    )
    assert r.status_code == 200

    # The email mock must have been called — if not, the endpoint is a stub
    mock_email.assert_called_once(), (
        "Password reset endpoint returned 200 but never called email service. "
        "This is a stub — DEFECT-001."
    )
```

### 11.2 Unauthenticated Route Grouping (DEFECT-002)

```python
# tests/security/test_auth_bypass.py
@pytest.mark.security
async def test_route_grouping_requires_authentication(client: AsyncClient):
    """
    Route grouping endpoints must require a valid auth token.
    Currently accessible without any token (DEFECT-002).
    """
    r = await client.get("/api/v1/route-grouping/")
    assert r.status_code in (401, 403), (
        f"Route grouping endpoint is publicly accessible (returned {r.status_code}). "
        "DEFECT-002: All permission checks are commented out."
    )

@pytest.mark.security
async def test_push_notification_send_requires_authentication(client: AsyncClient):
    """
    Push notification send endpoint must require auth (DEFECT-003).
    """
    r = await client.post(
        "/api/v1/push-notifications/send",
        json={"title": "Test", "body": "Test", "recipient_ids": [1]},
    )
    assert r.status_code in (401, 403), (
        f"Push notification endpoint is publicly accessible (returned {r.status_code}). "
        "DEFECT-003: No auth dependency on push notification router."
    )
```

---

## 12. `scripts/run_tests.sh`

```bash
#!/usr/bin/env bash
# scripts/run_tests.sh
set -euo pipefail

SUITE=${1:-smoke}
ENV_FILE=".env.test"

if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

case "$SUITE" in
  smoke)
    echo "Running SMOKE tests..."
    pytest tests/ -m smoke --tb=short -v
    ;;
  unit)
    echo "Running UNIT tests..."
    pytest tests/unit/ --tb=short -v --cov=app --cov-report=term-missing
    ;;
  integration)
    echo "Running INTEGRATION tests..."
    pytest tests/integration/ -m integration --tb=short -v -n auto --dist=loadgroup
    ;;
  security)
    echo "Running SECURITY tests..."
    pytest tests/security/ -m security --tb=long -v
    ;;
  api)
    echo "Running API tests..."
    pytest tests/api/ --tb=short -v
    ;;
  all)
    echo "Running FULL test suite..."
    pytest tests/ --tb=short -v -n auto --dist=loadgroup \
      --cov=app --cov-report=html:reports/coverage \
      --html=reports/report.html --self-contained-html \
      --alluredir=reports/allure-results
    ;;
  *)
    echo "Usage: $0 [smoke|unit|integration|security|api|all]"
    exit 1
    ;;
esac
```

---

*End of Automation Plan*
