# Fleet Manager — Codebase Audit Report

**Date:** 2026-04-30  
**Auditor:** Senior Backend Architect  
**Scope:** Full codebase review — `app/`, `migrations/`, `main.py`, `common_utils/`

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 9 |
| High | 14 |
| Medium | 11 |
| Low | 7 |
| **Total** | **41** |

---

## CRITICAL Issues

---

### AUDIT-001 — Broken Password Verification (Double-Hashing)

**File:** `app/routes/auth_router.py:531`  
**Severity:** Critical  
**SOLID Violation:** None — pure security bug

**Current Code:**
```python
if not verify_password(hash_password(form_data.password), employee.password):
```

**Explanation:**  
`hash_password()` is called on the plaintext password before passing it to `verify_password()`. `verify_password` is a bcrypt comparison function — it expects a plaintext password and a hash. By pre-hashing the input, you are passing a bcrypt digest of a bcrypt digest. This comparison will **always fail** for bcrypt. The only reason logins currently work is if `verify_password` is doing something non-standard (e.g., comparing hashes directly), which would mean passwords are not being verified at all.

**Suggested Fix:**
```python
if not verify_password(form_data.password, employee.password):
```

---

### AUDIT-002 — Hardcoded Secret Key Default

**File:** `app/config.py:94`  
**Severity:** Critical

**Current Code:**
```python
SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey")
```

**Explanation:**  
`"supersecretkey"` is a trivially guessable JWT signing key. Any deployment that fails to set `SECRET_KEY` in environment will have all JWTs forgeable. This is a production-blocking security vulnerability.

**Suggested Fix:**
```python
SECRET_KEY: str  # No default — will raise ValidationError if not set in env
```
Add a validator that raises an error if the key length is less than 32 characters.

---

### AUDIT-003 — OTP Generated with `random` Module (Not Cryptographically Secure)

**File:** `app/routes/auth_router.py:818`  
**Severity:** Critical

**Current Code:**
```python
otp = str(random.randint(100000, 999999))
```

**Explanation:**  
Python's `random` module uses a Mersenne Twister PRNG which is not cryptographically secure. An attacker who observes enough OTPs can predict future ones. Authentication OTPs must be generated with `secrets.randbelow()`.

**Suggested Fix:**
```python
import secrets
otp = str(secrets.randbelow(900000) + 100000)
```

---

### AUDIT-004 — Duplicate Imports in auth_router.py (Dead Code Risk)

**File:** `app/routes/auth_router.py:36–60`  
**Severity:** Critical (indicates lack of code review; the duplicate block shadows the first)

**Current Code:**
```python
# Lines 36-39
from common_utils.auth.utils import (
    create_access_token, create_refresh_token, 
    verify_token, hash_password, verify_password
)
from common_utils.auth.token_validation import Oauth2AsAccessor, validate_bearer_token
# ...
# Lines 50-54 — EXACT DUPLICATE
from common_utils.auth.utils import (
    create_access_token, create_refresh_token, 
    verify_token, hash_password, verify_password
)
from common_utils.auth.token_validation import Oauth2AsAccessor, validate_bearer_token
```

**Explanation:**  
Modules are imported twice. Python will silently deduplicate the import, but this pattern signals the file has grown by copy-paste without review. Other duplicated imports on lines 42-60 include `employee_crud`, `admin_crud`, `driver_crud`, `get_logger`, `ResponseWrapper`. This inflates the file and increases cognitive overhead.

**Suggested Fix:** Remove all duplicate import blocks. Run `isort` and `flake8` as pre-commit hooks.

---

### AUDIT-005 — Missing Foreign Key on `route_management_bookings.booking_id`

**File:** `app/models/route_management.py:66`  
**Severity:** Critical — Data Integrity

**Current Code:**
```python
booking_id = Column(Integer, nullable=False)
```

**Explanation:**  
`RouteManagementBooking.booking_id` references the `bookings` table but has no `ForeignKey` constraint. This allows orphaned route_management_booking records pointing to deleted bookings. The codebase already has guard logic that logs warnings about missing bookings (`booking_obj` not found) — this is the root cause.

**Suggested Fix:**
```python
booking_id = Column(
    Integer,
    ForeignKey("bookings.booking_id", ondelete="CASCADE"),
    nullable=False
)
```
Add a corresponding Alembic migration and add the relationship to `RouteManagementBooking`.

---

### AUDIT-006 — Missing Foreign Keys on `route_management` Assignment Columns

**File:** `app/models/route_management.py:33–34`  
**Severity:** Critical — Data Integrity

**Current Code:**
```python
assigned_vendor_id = Column(Integer, nullable=True)
assigned_vehicle_id = Column(Integer, nullable=True)
assigned_driver_id = Column(Integer, nullable=True)
```

**Explanation:**  
These three columns reference `vendors`, `vehicles`, and `drivers` respectively but have no FK constraints. A vendor/vehicle/driver can be deleted while routes still reference them, causing silent null-lookups and NoneType errors at runtime.

**Suggested Fix:**
```python
assigned_vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True)
assigned_vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"), nullable=True)
assigned_driver_id = Column(Integer, ForeignKey("drivers.driver_id", ondelete="SET NULL"), nullable=True)
```

---

### AUDIT-007 — Development OTP Exposed in API Response

**File:** `app/routes/auth_router.py:922–925`  
**Severity:** Critical — Information Disclosure

**Current Code:**
```python
if settings.ENV == "development":
    response_data["otp_dev"] = otp
    response_data["note"] = "OTP included for development testing only"
```

**Explanation:**  
If `ENV` is misconfigured or defaults to `"development"` in a production container, the OTP is returned in the HTTP response body, making OTP-based auth completely bypassable. This is a critical secret disclosure vulnerability.

**Suggested Fix:** Remove entirely. Use a separate test fixture or seed mechanism. If needed, gate on `ENV == "development"` AND `DEBUG == True` AND log to file/stdout only — never to the API response.

---

### AUDIT-008 — Synchronous Alembic Migration Run Inside Async Lifespan

**File:** `main.py:79`  
**Severity:** Critical — Availability

**Current Code:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(force_configure=True)
    run_migrations()  # sync function inside async context
```

**Explanation:**  
`run_migrations()` is a blocking synchronous call. When called inside an async lifespan context, it blocks the event loop during startup, preventing uvicorn from accepting health checks. In Kubernetes, this will cause liveness probe failures and premature pod restarts during migrations on large tables.

**Suggested Fix:**
```python
import asyncio
from functools import partial

async def lifespan(app: FastAPI):
    await asyncio.get_event_loop().run_in_executor(None, run_migrations)
    yield
```

---

### AUDIT-009 — `sa` Import Used Before It Is Defined in session_manager.py

**File:** `app/services/session_manager.py:248`  
**Severity:** Critical — Runtime Error

**Current Code:**
```python
# Line 248 — uses sa.tuple_
sessions = self.db.query(UserSession).filter(
    UserSession.is_active == True,
    sa.tuple_(UserSession.user_type, UserSession.user_id).in_(user_keys)
).all()
# ...
# Line 479 — import placed AFTER usage
import sqlalchemy as sa
```

**Explanation:**  
`sqlalchemy` is imported as `sa` at line 479, after it is used at line 248. This causes a `NameError` whenever `get_active_sessions_batch()` is called. The module-level import was placed at the bottom as a note to "avoid circular import" — but that is incorrect (no circular import exists here). This means batch push notification delivery silently fails.

**Suggested Fix:** Move `import sqlalchemy as sa` to the top of the file. There is no circular dependency.

---

## HIGH Issues

---

### AUDIT-010 — Massive Route Functions Violating Single Responsibility Principle (SRP)

**File:** `app/routes/booking_router.py`  
**Severity:** High  
**SOLID Violation:** SRP — Single Responsibility Principle

**Explanation:**  
`create_booking()` is ~300 lines. `get_bookings()` is ~250 lines. Each route function performs: auth validation, business rule validation, cache retrieval, DB queries, response serialization, and error handling. This should be split across dedicated service, validator, and serializer layers.

**Suggested Fix:** Extract into:
- `app/services/booking_service.py` — business logic
- `app/validators/booking_validator.py` — validation rules
- `app/serializers/booking_serializer.py` — response building

---

### AUDIT-011 — Massive Code Duplication: Route Details Block Copied Verbatim

**File:** `app/routes/booking_router.py:499–660` and `app/routes/booking_router.py:760–918`  
**Severity:** High  
**SOLID Violation:** DRY / OCP

**Explanation:**  
The entire block for fetching and building route details (vehicle, driver, vendor, shift, passengers) is **copy-pasted identically** between `get_bookings()` and `get_bookings_by_employee()`. This is ~160 lines of duplicated code. Any bug fix or feature change requires updating both copies.

**Suggested Fix:**
```python
def _build_route_detail_map(db, booking_ids, tenant_id) -> dict:
    """Returns a dict of booking_id -> route_info dict"""
    ...
```
Call from both endpoints.

---

### AUDIT-012 — `get_logger()` Clears Handlers on Every Call

**File:** `app/core/logging_config.py:171`  
**Severity:** High — Performance & Correctness

**Current Code:**
```python
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers = []  # ← clears on every call
    logger.propagate = True
    logger.disabled = False
    return logger
```

**Explanation:**  
Every call to `get_logger()` (which is called at module import time in ~30 files) resets `logger.handlers`. While this appears harmless because handlers propagate to the root, it is a performance anti-pattern that runs every time a module is imported. It also makes it impossible to add per-module file handlers. Python's `logging.getLogger` is already a singleton — handlers should only be configured once.

**Suggested Fix:**
```python
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.propagate = True
    logger.disabled = False
    return logger
```
Remove `logger.handlers = []`.

---

### AUDIT-013 — `CacheManager` Creates Redis Connection at Module Import Time

**File:** `app/utils/cache_manager.py:18–28, 64`  
**Severity:** High

**Current Code:**
```python
class CacheManager:
    def __init__(self):
        self.redis_client = redis.Redis(...)  # Connects immediately

cache = CacheManager()  # Module-level instantiation
```

**Explanation:**  
`CacheManager()` is instantiated at module import. If Redis is unavailable at startup (common in Docker Compose race conditions), this raises a connection error during import of any module that imports `cache_manager`. Redis's `redis.Redis` uses lazy connection by default, but `socket_connect_timeout=5` triggers an immediate connection test.

**Suggested Fix:** Use lazy initialization or `ConnectionPool` with explicit `ping` in the health check:
```python
pool = redis.ConnectionPool(host=..., port=..., ...)
self.redis_client = redis.Redis(connection_pool=pool)
```

---

### AUDIT-014 — Redundant `os.getenv()` Calls Inside Pydantic `BaseSettings`

**File:** `app/config.py:6–153`  
**Severity:** High — Redundant/Misleading Code

**Current Code:**
```python
class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "development")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    # etc.
```

**Explanation:**  
`pydantic-settings`'s `BaseSettings` already reads from environment variables automatically. The `os.getenv()` calls are redundant and misleading — they run at class definition time, not at instance creation. This means the fallback defaults in `os.getenv()` may differ from Pydantic's default handling. Setting `env_file=".env"` in `model_config` is already correct; just define the field defaults directly:

**Suggested Fix:**
```python
class Settings(BaseSettings):
    ENV: str = "development"
    POSTGRES_HOST: str = "localhost"
    SECRET_KEY: str  # Required — no default
```

---

### AUDIT-015 — `GenderEnum` Defined in Three Separate Files

**Files:** `app/models/employee.py:10`, `app/models/driver.py:13`, `app/models/shift.py:19`  
**Severity:** High  
**SOLID Violation:** DRY

**Explanation:**  
`GenderEnum` is duplicated identically across employee, driver, and shift models. Any change (e.g., adding "Non-binary") must be applied in three places, risking inconsistency.

**Suggested Fix:** Create `app/models/enums.py` with all shared enums:
```python
class GenderEnum(str, PyEnum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
```
Import from the shared module in all model files.

---

### AUDIT-016 — `print()` Used for Cache Error Logging

**File:** `app/utils/cache_manager.py:36, 44, 53, 61`  
**Severity:** High

**Current Code:**
```python
except Exception as e:
    print(f"Cache get error: {e}")
    return None
```

**Explanation:**  
`print()` bypasses the structured logging system entirely. These errors will not appear in monitoring tools, will not carry request IDs, and cannot be filtered by log level. In production, they will appear as raw stdout noise mixed with access logs.

**Suggested Fix:**
```python
from app.core.logging_config import get_logger
logger = get_logger(__name__)
# ...
logger.warning("Cache get error: %s", e)
```

---

### AUDIT-017 — Hardcoded CORS Origins Including Production Domains

**File:** `main.py:144–147`  
**Severity:** High

**Current Code:**
```python
_cors_origins = [
    "*",
    "http://localhost:3000",
    "https://test.euronext.gocab.tech",
    "https://euronext.gocab.tech",
    "https://api.gocab.tech",
]
```

**Explanation:**  
Production domain names are hardcoded in source code. This: (1) exposes client domain names in the repository, (2) makes it impossible to deploy the same image for different clients without code changes, (3) includes `"*"` which makes all other allowed origins redundant (wildcard overrides specific origins in browser CORS).

**Suggested Fix:** Read exclusively from `CORS_ORIGINS` env variable. Remove wildcard `"*"` from the list. If `CORS_ORIGINS` is unset, default to `["http://localhost:3000"]` only in non-production environments.

---

### AUDIT-018 — `datetime.utcnow()` Used (Deprecated, Timezone-Naive)

**Files:** `app/services/session_manager.py:109, 133, 134, 287, 349, 389, 404`  
**Severity:** High

**Explanation:**  
`datetime.utcnow()` is deprecated since Python 3.12 and returns timezone-naive datetime objects. Comparing these with timezone-aware datetimes (which Postgres returns) causes `TypeError`. All timestamps should be timezone-aware UTC.

**Suggested Fix:**
```python
from datetime import datetime, timezone
datetime.now(timezone.utc)  # timezone-aware UTC
```

---

### AUDIT-019 — `BackgroundTasks` Instantiated as Default Parameter

**File:** `app/routes/auth_router.py:768`  
**Severity:** High

**Current Code:**
```python
async def request_employee_otp(
    form_data: OTPRequestSchema = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),  # Wrong
    db: Session = Depends(get_db)
):
```

**Explanation:**  
`BackgroundTasks` must be declared as a FastAPI dependency injection parameter, not instantiated as a default. Using `BackgroundTasks()` as a default value creates a single shared instance across requests. The correct pattern is `background_tasks: BackgroundTasks` (no default), which FastAPI injects per-request.

**Suggested Fix:**
```python
async def request_employee_otp(
    form_data: OTPRequestSchema = Body(...),
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
```

---

### AUDIT-020 — Prometheus Metrics Endpoint Exposed Without Authentication

**File:** `main.py:121`  
**Severity:** High

**Current Code:**
```python
.expose(app, endpoint="/metrics", include_in_schema=False)
```

**Explanation:**  
The `/metrics` endpoint is publicly accessible with no authentication. Prometheus metrics expose internal system details (request rates, error rates, memory usage) that attackers can use for reconnaissance.

**Suggested Fix:** Add IP allowlist middleware or HTTP Basic Auth for `/metrics`, or restrict to internal network only via reverse proxy (nginx/traefik `allow` directives).

---

### AUDIT-021 — Route Booking's `get_booking_by_id` Has N+1 Queries

**File:** `app/routes/booking_router.py:971–1031`  
**Severity:** High — Performance

**Explanation:**  
`get_booking_by_id` executes individual queries for: route_booking → route → all_route_bookings → all_bookings → all_employees → vehicle → driver → vendor → shift. This is 7+ sequential queries where 2 are sufficient with proper eager loading. See `query_optimization.md` for the optimized version.

---

### AUDIT-022 — `booking_router.py` Directly Queries DB Models (Bypasses CRUD Layer)

**File:** `app/routes/booking_router.py:161–168, 304–313`  
**Severity:** High  
**SOLID Violation:** SRP, Layered Architecture

**Explanation:**  
Route handlers directly call `db.query(Employee)`, `db.query(Booking)`, `db.query(RouteManagement)` etc. The codebase has a CRUD layer (`app/crud/`) that is intended to encapsulate all DB access. Routes bypass it, creating two parallel data access paths and making it impossible to add cross-cutting concerns (audit logging, caching) at the data layer.

---

### AUDIT-023 — Cache Serialization Functions Are Massively Duplicated

**File:** `app/utils/cache_manager.py:596–1125`  
**Severity:** High  
**SOLID Violation:** DRY

**Explanation:**  
There are 8 nearly identical `serialize_X_for_cache` / `deserialize_X_from_cache` function pairs (~500 lines total). Each function: reads all column values, converts datetimes to ISO strings, converts special types, and reconstructs the model. This pattern can be replaced by a single generic serializer.

**Suggested Fix:**
```python
def serialize_model_for_cache(model_instance) -> dict:
    from sqlalchemy import inspect
    mapper = inspect(type(model_instance))
    result = {}
    for col in mapper.columns:
        value = getattr(model_instance, col.key)
        if isinstance(value, datetime):
            result[col.key] = value.isoformat()
        elif hasattr(value, 'isoformat'):  # date, time
            result[col.key] = value.isoformat()
        elif hasattr(value, 'value'):  # Enum
            result[col.key] = value.value
        else:
            result[col.key] = value
    return result
```

---

## MEDIUM Issues

---

### AUDIT-024 — `extend_existing=True` on All Models Hides Schema Conflicts

**Files:** `app/models/booking.py:28`, `app/models/employee.py:41`, `app/models/tenant.py:8`, all other models  
**Severity:** Medium

**Explanation:**  
`extend_existing=True` in `__table_args__` suppresses SQLAlchemy's duplicate table definition error. This is a workaround for models being imported from multiple places. While harmless at runtime, it hides situations where two model definitions disagree on column definitions.

**Suggested Fix:** Ensure models are imported only once through `app/models/__init__.py`. Remove `extend_existing=True` once circular import issues are resolved.

---

### AUDIT-025 — `setup_logging()` Called at Module Import Level in logging_config.py

**File:** `app/core/logging_config.py:177`  
**Severity:** Medium

**Current Code:**
```python
# Line 177 — at module level
setup_logging(force_configure=True)
```

**Explanation:**  
Calling `setup_logging()` at module import time means logging is configured whenever any file imports from `logging_config.py`. This interferes with test isolation (tests can't customize logging) and runs before the application configuration is fully loaded.

**Suggested Fix:** Remove the module-level call. Only call it explicitly from `main.py` at startup.

---

### AUDIT-026 — Voter Logic in `get_employee_roles_and_permissions` Uses O(n) Linear Search

**File:** `app/crud/employee.py:155`  
**Severity:** Medium — Performance

**Current Code:**
```python
existing = next((p for p in all_permissions if p["module"] == module), None)
```

**Explanation:**  
For each permission, a linear scan of `all_permissions` is performed to find an existing module entry. For employees with many permissions, this is O(n²). The same pattern is repeated in `auth_router.py:147`.

**Suggested Fix:** Use a dictionary keyed by module name:
```python
permissions_by_module: dict[str, list] = {}
# ...
if module not in permissions_by_module:
    permissions_by_module[module] = []
permissions_by_module[module].append(action)
```

---

### AUDIT-027 — `PolicyPackage.permission_ids` Stored as JSON Array, Not Relational

**File:** `app/models/iam/policy.py:28`  
**Severity:** Medium — Data Integrity

**Current Code:**
```python
permission_ids = Column(JSON, nullable=False, default=list)
```

**Explanation:**  
Storing an array of foreign key IDs in a JSON column bypasses referential integrity. If a `Permission` row is deleted, the `PolicyPackage.permission_ids` array is not cleaned up, leading to stale IDs. A proper junction table (`iam_package_permissions`) would provide FK constraints.

---

### AUDIT-028 — `RouteManagementBooking` Time Fields Stored as String(10) Instead of Time

**File:** `app/models/route_management.py:69, 72–74`  
**Severity:** Medium

**Current Code:**
```python
estimated_pick_up_time = Column(String(10), nullable=True)
actual_pick_up_time = Column(String(10), nullable=True)
estimated_drop_time = Column(String(10), nullable=True)
actual_drop_time = Column(String(10), nullable=True)
```

**Explanation:**  
Time values stored as strings cannot be compared, sorted, or queried by range in SQL. This makes route timing analysis impossible at the DB layer.

**Suggested Fix:** Use `Column(Time, nullable=True)` or `Column(DateTime, nullable=True)` depending on whether date context is needed.

---

### AUDIT-029 — `OTP` for Boarding/Deboarding Stored as Integer

**File:** `app/models/booking.py:40–41`  
**Severity:** Medium — Security

**Current Code:**
```python
boarding_otp = Column(Integer, nullable=True)
deboarding_otp = Column(Integer, nullable=True)
```

**Explanation:**  
OTPs should be stored as hashed strings (bcrypt or SHA-256), not plaintext integers. A DB compromise exposes all active OTPs.

---

### AUDIT-030 — `ERROR_TRACKER` Stores Errors in Process Memory

**File:** `app/middleware/error_tracking.py:21–26`  
**Severity:** Medium — Reliability

**Explanation:**  
`ErrorTracker.errors` is a plain Python list capped at 1000 entries. In a multi-process deployment (gunicorn with multiple workers), each worker has its own list. Errors are lost on restart. This should use Redis for persistence and cross-process aggregation.

---

### AUDIT-031 — Sensitive Config Values Logged at Startup

**File:** `main.py:35`  
**Severity:** Medium — Security

**Current Code:**
```python
logger.info("🚀 Fleet Manager starting — env: %s", settings)
```

**Explanation:**  
`settings` is logged as a string. Pydantic's default `__repr__` for `BaseSettings` includes all field values, which means `SMTP_PASSWORD`, `TWILIO_AUTH_TOKEN`, `SECRET_KEY`, and database credentials are written to logs on every startup.

**Suggested Fix:**
```python
logger.info("Fleet Manager starting — ENV=%s VERSION=%s", settings.ENV, settings.APP_VERSION)
```

---

### AUDIT-032 — No Rate Limiting on Authentication Endpoints

**Files:** `app/routes/auth_router.py` — all login/OTP endpoints  
**Severity:** Medium — Security

**Explanation:**  
No rate limiting is applied to `/auth/employee/login`, `/auth/employee/request-otp`, or `/auth/employee/verify-otp`. This allows brute-force attacks against employee accounts without restriction, especially since the OTP has only 3 attempts but a new OTP can be immediately requested after expiry.

**Suggested Fix:** Implement `slowapi` or `fastapi-limiter` on these endpoints:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)

@router.post("/employee/login")
@limiter.limit("10/minute")
async def employee_login(...):
```

---

### AUDIT-033 — No Input Sanitization on Search/Filter Parameters

**File:** `app/crud/employee.py:83`  
**Severity:** Medium — Security

**Current Code:**
```python
search_pattern = f"%{search_term}%"
return db.query(Employee).filter(Employee.name.ilike(search_pattern), ...)
```

**Explanation:**  
`search_term` is used directly in a LIKE pattern. While SQLAlchemy parameterizes the query (preventing SQL injection), a search term like `%%%%%` can cause catastrophically slow queries. Input length and character allowlisting should be applied.

---

### AUDIT-034 — `expire_on_commit=False` Not Set — Lazy Load After Commit

**File:** `app/database/session.py:19`  
**Severity:** Medium

**Explanation:**  
`SessionLocal` uses default `expire_on_commit=True`. After a `db.commit()`, all loaded ORM objects are expired, meaning any attribute access triggers a new DB query. In route handlers that access model attributes after `commit()` (common in the booking flow), this creates implicit hidden queries.

---

## LOW Issues

---

### AUDIT-035 — `ALLOWED_FILE_TYPES` List in Settings Cannot Be Set from Env

**File:** `app/config.py:91`  
**Severity:** Low

**Current Code:**
```python
ALLOWED_FILE_TYPES: list = ["image/jpeg", "image/png", "application/pdf"]
```

**Explanation:**  
Pydantic `BaseSettings` cannot parse a list from an environment variable without a custom validator. This value can never be overridden without code changes.

---

### AUDIT-036 — `ACCESS_TOKEN_EXPIRE_MINUTES` Not Used (TOKEN_EXPIRY_HOURS Used Instead)

**File:** `app/config.py:96–97`  
**Severity:** Low — Dead Code

**Current Code:**
```python
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60*24  # Hardcoded, not read from env
TOKEN_EXPIRY_HOURS: int = int(os.getenv("TOKEN_EXPIRY_HOURS", "24"))  # Used in auth_router
```

**Explanation:**  
Two settings control token expiry, but only `TOKEN_EXPIRY_HOURS` is used. `ACCESS_TOKEN_EXPIRE_MINUTES` is dead configuration.

---

### AUDIT-037 — Typo in Source File Name

**File:** `app/utils/validition.py`  
**Severity:** Low

**Explanation:**  
The file is named `validition.py` instead of `validation.py`. This is a typo that causes confusion and may break IDE navigation.

---

### AUDIT-038 — Comment Inconsistency: Route Numbers Duplicated

**File:** `app/routes/booking_router.py:291, 303`  
**Severity:** Low

**Current Code:**
```python
# 3️⃣ Prevent booking if shift time has already passed today
# ...
# 3️⃣ Duplicate booking check
```

**Explanation:**  
Two consecutive code sections are both labeled `3️⃣`. This indicates a refactoring that was left incomplete.

---

### AUDIT-039 — Typo in File Name: `optimal_roiute_generation.py`

**File:** `app/services/optimal_roiute_generation.py`  
**Severity:** Low

**Explanation:**  
Filename contains a typo: `roiute` instead of `route`.

---

### AUDIT-040 — `common_utils` Is a Flat Directory Not a Proper Package

**File:** `common_utils/`  
**Severity:** Low

**Explanation:**  
`common_utils` is imported as a package but its structure and versioning is unclear. It should be extracted into a proper internal package with its own `pyproject.toml` and versioned separately from the main app.

---

### AUDIT-041 — Voice/WhatsApp Notification Handlers Return `True` Without Implementation

**File:** `app/services/notification_service.py:388, 414`  
**Severity:** Low

**Current Code:**
```python
# Return True for testing
return True
```

**Explanation:**  
Voice and WhatsApp notification channels are marked as successfully sent but no actual message is delivered. Alert logs will show these channels as `SENT` when they were never attempted. This misleads ops teams during incidents.

---

## Appendix: SOLID Violations Summary

| Issue | Principle Violated | Description |
|-------|-------------------|-------------|
| AUDIT-010 | SRP | Route functions perform auth, business logic, caching, and serialization |
| AUDIT-011 | DRY/OCP | Route detail block duplicated across two endpoints |
| AUDIT-014 | DRY | Redundant `os.getenv()` inside `BaseSettings` |
| AUDIT-015 | DRY | `GenderEnum` defined in 3 model files |
| AUDIT-022 | SRP/Layered | Routes bypass CRUD layer and query DB directly |
| AUDIT-023 | DRY | 8 nearly-identical serialize/deserialize function pairs |
| AUDIT-026 | Performance/DRY | O(n²) permission aggregation repeated in 2 files |
