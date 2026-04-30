# Fleet Manager — Refactor Plan

**Date:** 2026-04-30  
**Scope:** Four phased refactoring stages — Security Hardening → Architecture → Performance → Code Quality  
**Principle:** No breaking changes within a phase. Each phase is independently deployable and testable.  
**Cross-reference:** `audit_report.md`, `production_gaps.md`, `db_analysis.md`, `query_optimization.md`

---

## Execution Philosophy

- **Do not refactor everything at once.** Each phase produces a deployable diff.
- **Write tests before refactoring**, not after.
- **Run the full test suite** (`pytest -x`) before and after each task.
- **Open one PR per task**, not one PR per phase, to enable parallel review.
- Severity labels map to audit/gap issue IDs for traceability.

---

## Phase 1 — Security Hardening (Priority P0/P1)

**Goal:** Fix all issues that can result in authentication bypass, credential exposure, or privilege escalation. No architectural changes; these are surgical fixes.

**Estimated effort:** 2–3 engineer-days  
**Blocking for production:** Yes — none of these can be deferred.

---

### Task 1.1 — Fix Broken Password Verification

**File:** `app/routes/auth_router.py:531`  
**Ref:** AUDIT-001  
**Change:**
```python
# Before
if not verify_password(hash_password(form_data.password), employee.password):

# After
if not verify_password(form_data.password, employee.password):
```
**Test:** Add `test_employee_login_correct_password_succeeds` and `test_employee_login_wrong_password_fails` to `tests/test_auth.py`.

---

### Task 1.2 — Replace `random.randint` with `secrets` for OTP Generation

**File:** `app/routes/auth_router.py:818`  
**Ref:** AUDIT-003  
**Change:**
```python
# Before
import random
otp = str(random.randint(100000, 999999))

# After
import secrets
otp = str(secrets.randbelow(900000) + 100000)
```
**Test:** Assert `len(otp) == 6` and `100000 <= int(otp) <= 999999` in 10,000 iterations.

---

### Task 1.3 — Remove OTP Dev Leak from API Response

**File:** `app/routes/auth_router.py:922–925`  
**Ref:** AUDIT-007, PG-008  
**Change:** Delete the entire `if settings.ENV == "development": response_data["otp_dev"] = otp` block.  
**Migration path:** Use `pytest` fixtures or a test-only endpoint in the test environment that reads the OTP from a mocked `secrets` call.

---

### Task 1.4 — Remove Hardcoded Secret Defaults from `config.py`

**File:** `app/config.py`  
**Ref:** AUDIT-002, PG-003  
**Change:**
```python
# Before
SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey")

# After — field with validator (no default)
from pydantic import field_validator

class Settings(BaseSettings):
    SECRET_KEY: str  # Required

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v
```
Also remove defaults for `POSTGRES_PASSWORD` and `DATABASE_URL` (require explicit env values).

---

### Task 1.5 — Remove Plaintext Secrets from docker-compose Files

**Files:** `docker-compose.yml`, `docker-compose_prod.yaml`  
**Ref:** PG-001, PG-004  
**Actions:**
1. Rotate SMTP App Password (`orls draa fbxo neox`) immediately.
2. Remove all secret values from compose files; replace with `${VAR_NAME}` references.
3. Create `.env.example` with placeholder values and documentation.
4. Add `.env` and `service.prod.env` to `.gitignore`.
5. Scrub git history: `git filter-repo --path docker-compose_prod.yaml --invert-paths` is not appropriate here since the prod compose is needed — instead scrub the specific lines using `git filter-repo --replace-text` to remove the literal credential values.

---

### Task 1.6 — Clean Up Duplicate Imports in auth_router.py

**File:** `app/routes/auth_router.py:36–60`  
**Ref:** AUDIT-004  
**Change:** Remove the second block of duplicate imports (lines ~50–60). Run `isort app/routes/auth_router.py`.  
**Add:** `isort` and `flake8` (or `ruff`) as pre-commit hooks in `.pre-commit-config.yaml`.

---

### Task 1.7 — Fix `BackgroundTasks` Instantiation

**File:** `app/routes/auth_router.py:768`  
**Ref:** AUDIT-019  
**Change:**
```python
# Before
async def request_employee_otp(
    ...,
    background_tasks: BackgroundTasks = BackgroundTasks(),  # wrong
    ...
):

# After
async def request_employee_otp(
    ...,
    background_tasks: BackgroundTasks,  # FastAPI injects per-request
    ...
):
```

---

### Task 1.8 — Restrict `/metrics` Endpoint

**File:** `main.py:121`  
**Ref:** AUDIT-020, PG-007  
**Change:** Add HTTP Basic Auth middleware for `/metrics` using settings values `METRICS_USER` and `METRICS_PASSWORD`. Add both fields to `Settings` (required, no defaults).

---

### Task 1.9 — Fix Startup Logging: Do Not Log Full Settings Object

**File:** `main.py:35`  
**Ref:** AUDIT-031, PG-015  
**Change:**
```python
# Before
logger.info("🚀 Fleet Manager starting — env: %s", settings)

# After
logger.info(
    "Fleet Manager starting — ENV=%s VERSION=%s DB_HOST=%s",
    settings.ENV, settings.APP_VERSION, settings.POSTGRES_HOST
)
```

---

## Phase 2 — Architecture Refactor (Priority P1/P2)

**Goal:** Establish proper layering, eliminate cross-cutting violations, and fix structural bugs.  
**Estimated effort:** 5–7 engineer-days  
**Blocking for production:** Most items in this phase should be completed before sustained production load.

---

### Task 2.1 — Fix `sa` Import Order in session_manager.py

**File:** `app/services/session_manager.py:479`  
**Ref:** AUDIT-009  
**Change:** Move `import sqlalchemy as sa` from line 479 to the top of the file (line 1–15 import block).  
This is a **one-line fix** but a **critical runtime bug** — `get_active_sessions_batch()` raises `NameError` as-is.

---

### Task 2.2 — Run Alembic Migrations in Init Container, Not App Lifespan

**Files:** `main.py:79`, `docker-compose.yml`  
**Ref:** AUDIT-008, PG-009, PG-010  
**Change (compose):**
```yaml
services:
  migrate:
    image: dheerajkumarp/fleet_service_manager:latest
    command: alembic upgrade head
    depends_on:
      postgres:
        condition: service_healthy
    env_file: .env

  fleet_api:
    depends_on:
      migrate:
        condition: service_completed_successfully
```

**Change (main.py):** Remove `run_migrations()` call from lifespan. Keep it as an importable function for local dev convenience but do not call it automatically.

---

### Task 2.3 — Extract Service Layer for Booking Logic

**Files:** `app/routes/booking_router.py` (300-line functions), create `app/services/booking_service.py`  
**Ref:** AUDIT-010  
**Structure:**
```
app/
  services/
    booking_service.py       ← business logic: validate, create, cancel
  validators/
    booking_validator.py     ← date validation, shift rules, cutoff checks
  serializers/
    booking_serializer.py    ← _build_route_detail_map(), response building
  routes/
    booking_router.py        ← thin: auth check → service call → response
```

**Migration strategy:** Start with `create_booking` — extract each validation block into named functions in `booking_validator.py`, then move them to the validator module. This is incremental; the router stays functional at each step.

---

### Task 2.4 — Extract Deduplicated Route Detail Builder

**File:** `app/routes/booking_router.py:499–660` and `:760–918`  
**Ref:** AUDIT-011  
**Change:** Extract to `app/serializers/booking_serializer.py`:
```python
def build_route_detail_map(
    db: Session,
    booking_ids: list[int],
    tenant_id: str,
) -> dict[int, dict]:
    """Returns {booking_id: route_info_dict} for all booking_ids."""
    ...
```
Replace both usages with a call to this function.

---

### Task 2.5 — Centralize Shared Enums

**Files:** `app/models/employee.py:10`, `app/models/driver.py:13`, `app/models/shift.py:19`  
**Ref:** AUDIT-015  
**Change:**
1. Create `app/models/enums.py`:
```python
from enum import Enum as PyEnum

class GenderEnum(str, PyEnum):
    MALE   = "Male"
    FEMALE = "Female"
    OTHER  = "Other"
```
2. Replace all three inline definitions with:
```python
from app.models.enums import GenderEnum
```
3. Verify no migration is needed (`native_enum=False` means the DB stores a string value — the Python class name does not matter to the schema).

---

### Task 2.6 — Replace `os.getenv()` Calls Inside `BaseSettings`

**File:** `app/config.py`  
**Ref:** AUDIT-014  
**Change:**
```python
# Before
ENV: str = os.getenv("ENV", "development")

# After
ENV: str = "development"
```
Remove all `os.getenv()` calls from `Settings` field defaults. `BaseSettings` already handles env var loading. Remove the `import os` from `config.py` (except where `os.path.abspath` is used in the `STORAGE_BASE_URL` property — that stays).

---

### Task 2.7 — Fix `get_logger()` Handler Clearing

**File:** `app/core/logging_config.py:171`  
**Ref:** AUDIT-012  
**Change:**
```python
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    # Remove: logger.handlers = []
    logger.propagate = True
    logger.disabled = False
    return logger
```

---

### Task 2.8 — Remove Module-Level `setup_logging()` Call

**File:** `app/core/logging_config.py:177`  
**Ref:** AUDIT-025  
**Change:** Delete the module-level `setup_logging(force_configure=True)` call. It is already called explicitly in `main.py:33` and in the lifespan hook.

---

### Task 2.9 — Add DB Migration for Missing FK Constraints

**Files:** New migration files  
**Ref:** DB-001, DB-002, DB-003, DB-004 (`db_analysis.md`)  
**Change:** Create the following migrations (use `NOT VALID` + `VALIDATE CONSTRAINT` for zero-downtime):
1. `add_route_management_fk_constraints.py`
2. `add_route_management_bookings_booking_fk.py`
3. `add_missing_indexes.py`

See `db_analysis.md` Section 8 for the full SQL.

---

### Task 2.10 — Add Rate Limiting to Auth Endpoints

**Files:** `app/routes/auth_router.py`, `main.py`, `requirements.txt`  
**Ref:** AUDIT-032, PG-006  
**Change:**
1. Add `slowapi==0.1.9` to `requirements.txt`.
2. In `main.py`:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
limiter = Limiter(key_func=get_remote_address, storage_uri=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```
3. Decorate auth routes:
```python
@router.post("/employee/login")
@limiter.limit("10/minute")
async def employee_login(request: Request, ...):
```

---

## Phase 3 — Performance & Reliability (Priority P2)

**Goal:** Eliminate N+1 queries, fix ORM configuration, make the error tracker and cache production-safe.  
**Estimated effort:** 4–5 engineer-days  
**Blocking for production under load:** Yes.

---

### Task 3.1 — Add Eager Loading for Permission Resolution

**File:** `app/crud/employee.py:109`  
**Ref:** QO-006  
**Change:** Use `joinedload` for Employee → Role → Policies → Permissions in `get_employee_roles_and_permissions`. See `query_optimization.md` QO-006 for the exact query.

---

### Task 3.2 — Cache Resolved Permissions in Redis

**File:** `app/crud/employee.py:93–169`  
**Ref:** QO-006, QO-007  
**Change:** Wrap the entire permission resolution function output in a Redis cache keyed by `f"perms:{tenant_id}:{employee_id}"` with 5-minute TTL. Invalidate on:
- Role assignment change
- PolicyPackage update
- Employee deactivation

---

### Task 3.3 — Replace O(n²) Permission Aggregation with Dict

**Files:** `app/crud/employee.py:155`, `app/routes/auth_router.py:147`  
**Ref:** AUDIT-026, QO-005  
**Change:** See `query_optimization.md` QO-005 for the complete optimized implementation. Apply to both files.

---

### Task 3.4 — Remove Redundant COUNT Query in Paginated Bookings

**File:** `app/routes/booking_router.py:489`  
**Ref:** QO-001  
**Change:** Delete `filtered_count = query.count()`. Use `total` from `paginate_query` return value in the log statement.

---

### Task 3.5 — Batch Shift Lookups (Replace Per-ID Loop)

**Files:** `app/routes/booking_router.py:543–547` (and duplicate block in `get_bookings_by_employee`)  
**Ref:** QO-002  
**Change:** Replace per-shift-id loop with a single `IN ()` batch query. Write through to cache after fetching.

---

### Task 3.6 — Fix `get_booking_by_id` N+1 Queries

**File:** `app/routes/booking_router.py:971–1031`  
**Ref:** AUDIT-021, QO-004  
**Change:** Refactor to 3-query pattern using eager loading + `db.get()` for single-row FK lookups. See `query_optimization.md` QO-004 for the full optimized implementation.

---

### Task 3.7 — Set `expire_on_commit=False` in Session Factory

**File:** `app/database/session.py:19`  
**Ref:** AUDIT-034, QO-008  
**Change:**
```python
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)
```

---

### Task 3.8 — Replace Generic Serialize/Deserialize with `serialize_model()`

**File:** `app/utils/cache_manager.py:596–1125`  
**Ref:** AUDIT-023, QO-011  
**Change:** Implement the generic `serialize_model()` and `deserialize_model()` functions (see `query_optimization.md` QO-011). Replace all 8 specific serialize/deserialize function pairs with calls to the generic version.  
**Test:** Add unit tests for each model type to verify round-trip correctness.

---

### Task 3.9 — Move `ErrorTracker` Storage to Redis

**File:** `app/middleware/error_tracking.py`  
**Ref:** AUDIT-030, PG-011, PG-023  
**Change:**
```python
class ErrorTracker:
    def __init__(self):
        self.redis = redis.Redis(...)  # or use the shared pool

    def track(self, error: dict):
        ts = time.time()
        self.redis.zadd("error_tracker", {json.dumps(error): ts})
        self.redis.zremrangebyrank("error_tracker", 0, -1001)

    def get_recent(self, limit: int = 100) -> list:
        raw = self.redis.zrevrange("error_tracker", 0, limit - 1)
        return [json.loads(r) for r in raw]
```

---

### Task 3.10 — Fix `CacheManager` Eager Redis Connection

**File:** `app/utils/cache_manager.py:18–28, 64`  
**Ref:** AUDIT-013  
**Change:** Switch to `ConnectionPool` with lazy connection initialization:
```python
class CacheManager:
    def __init__(self):
        pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            socket_connect_timeout=5,
            decode_responses=True,
        )
        self.redis_client = redis.Redis(connection_pool=pool)
```
This still lazy-connects but now shares the pool across all `CacheManager` instances.

---

### Task 3.11 — Replace `print()` Statements with Structured Logging

**File:** `app/utils/cache_manager.py:36, 44, 53, 61`  
**Ref:** AUDIT-016  
**Change:**
```python
from app.core.logging_config import get_logger
logger = get_logger(__name__)

# Replace all print() calls:
logger.warning("Cache get error for key=%s: %s", key, e)
```

---

### Task 3.12 — Replace `datetime.utcnow()` with Timezone-Aware UTC

**File:** `app/services/session_manager.py:109, 133, 134, 287, 349, 389, 404`  
**Ref:** AUDIT-018  
**Change:**
```python
from datetime import datetime, timezone
# Replace all datetime.utcnow() with:
datetime.now(timezone.utc)
```
Search for all occurrences: `grep -rn "datetime.utcnow" app/`

---

## Phase 4 — Code Quality & Maintainability (Priority P3)

**Goal:** Improve long-term maintainability with no functional changes.  
**Estimated effort:** 2–3 engineer-days  
**Blocking for production:** No.

---

### Task 4.1 — Rename Typo Files

**Files:** `app/utils/validition.py`, `app/services/optimal_roiute_generation.py`  
**Ref:** AUDIT-037, AUDIT-039  
**Change:**
```bash
git mv app/utils/validition.py app/utils/validation.py
git mv app/services/optimal_roiute_generation.py app/services/optimal_route_generation.py
```
Update all import references. Check with `grep -rn "validition\|roiute" app/`.

---

### Task 4.2 — Fix `extend_existing=True` on All Models

**Files:** All models in `app/models/`  
**Ref:** AUDIT-024, DB-013  
**Change:**
1. Create `app/models/__init__.py` that imports every model exactly once in dependency order.
2. Audit all import sites to ensure models are only imported through `app.models`.
3. Remove `extend_existing=True` from all `__table_args__`.

---

### Task 4.3 — Create `app/models/enums.py` (Consolidate All Shared Enums)

**Ref:** AUDIT-015 (also depends on Task 2.5)  
This task is the completion of Task 2.5 — ensure all shared enums (`GenderEnum`, `BookingStatusEnum`, `RouteManagementStatusEnum`, etc.) are in one file and imported from there.

---

### Task 4.4 — Implement Voice and WhatsApp Notification Channels

**File:** `app/services/notification_service.py:388, 414`  
**Ref:** AUDIT-041  
**Change:** Implement using Twilio Voice API and Twilio WhatsApp API. If not implementable immediately, change the return value from `True` to `False` and set notification status to `SKIPPED` instead of `SENT`. Never mark a notification `SENT` without delivery confirmation.

---

### Task 4.5 — Remove Dead Config: `ACCESS_TOKEN_EXPIRE_MINUTES`

**File:** `app/config.py:96`  
**Ref:** AUDIT-036  
**Change:** Remove the unused `ACCESS_TOKEN_EXPIRE_MINUTES` field. Verify that only `TOKEN_EXPIRY_HOURS` is used in `auth_router.py`.

---

### Task 4.6 — Make `ALLOWED_FILE_TYPES` Configurable via Env

**File:** `app/config.py:91`  
**Ref:** AUDIT-035  
**Change:**
```python
from pydantic import field_validator

ALLOWED_FILE_TYPES: list[str] = ["image/jpeg", "image/png", "application/pdf"]

@field_validator("ALLOWED_FILE_TYPES", mode="before")
@classmethod
def parse_allowed_types(cls, v):
    if isinstance(v, str):
        return [t.strip() for t in v.split(",")]
    return v
```

---

### Task 4.7 — Add `/health` Endpoint

**Ref:** PG-018  
**Change:** Add `app/routes/health_router.py`:
```python
@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    try:
        cache.redis_client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    status_code = 200 if (db_ok and redis_ok) else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if status_code == 200 else "degraded",
                 "db": "ok" if db_ok else "error",
                 "redis": "ok" if redis_ok else "error"}
    )
```

---

### Task 4.8 — Add JSON Structured Logging for Production

**File:** `app/core/logging_config.py`  
**Ref:** PG-016  
**Change:** Add `JsonFormatter` class (see `production_gaps.md` PG-016). Use in production only:
```python
if settings.ENV == "production":
    handler.setFormatter(JsonFormatter())
else:
    handler.setFormatter(text_formatter)
```

---

### Task 4.9 — Add OTP Hashing for Boarding/Deboarding/Escort OTPs

**Files:** `app/models/booking.py:40–41`, `app/models/route_management.py:39`  
**Ref:** AUDIT-029, DB-010  
**Change:**
1. Write migration: `hash_otp_columns.py` — add `_hash` columns, backfill, drop originals.
2. Update all OTP write paths to call `hash_otp(otp)` before storing.
3. Update all OTP verification paths to call `verify_otp(plain, stored_hash)`.

---

## Phase Summary

| Phase | Tasks | Est. Days | Prod Blocking |
|-------|-------|-----------|---------------|
| **Phase 1** — Security Hardening | 9 | 2–3 | Yes |
| **Phase 2** — Architecture Refactor | 10 | 5–7 | Yes (2.1, 2.9) |
| **Phase 3** — Performance & Reliability | 12 | 4–5 | Yes (3.1–3.6) |
| **Phase 4** — Code Quality | 9 | 2–3 | No |
| **Total** | **40** | **13–18** | — |

---

## Dependency Graph

```
Phase 1 (all parallel, must finish before Phase 2):
  1.1 → 1.6 (clean imports then remove dupe)
  1.4 → 1.5 (config hardening, then compose cleanup)

Phase 2 (mostly parallel, key dependency: 2.2 before merging):
  2.1 (standalone critical fix)
  2.3 → 2.4 (service layer extract then dedup builder)
  2.5 → 4.2 → 4.3 (enum consolidation enables model cleanup)
  2.9 (DB migrations: independent, can run in parallel)

Phase 3 (requires Phase 2 complete for service layer tasks):
  3.1 → 3.2 (eager load, then cache)
  3.3 (standalone)
  3.4 → 3.5 → 3.6 (query optimizations in order)
  3.8 (requires 2.5 for generic serializer to work on all models)

Phase 4 (all deferred, non-blocking):
  4.1 (file rename — do early to avoid merge conflicts)
  4.9 (requires 3.x DB migration infrastructure)
```
