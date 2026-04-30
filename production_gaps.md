# Fleet Manager — Production Readiness Gaps

**Date:** 2026-04-30  
**Scope:** Security hardening, operational reliability, observability, deployment, and resilience  
**Cross-reference:** See `audit_report.md` for individual code-level issues; this document focuses on system-level gaps.

---

## Summary

| Category | Blocking for Prod | Non-Blocking |
|----------|:-----------------:|:------------:|
| Secrets & Credentials | 5 | — |
| Auth & Access Control | 3 | — |
| Infrastructure & Deployment | 4 | 2 |
| Observability & Logging | 2 | 3 |
| Reliability & Resilience | 4 | 1 |
| Data Integrity | 3 | — |
| Testing & CI | — | 3 |

---

## 1. BLOCKING — Secrets & Credentials

### PG-001 — Plaintext Secrets Committed in docker-compose.yml

**Files:** `docker-compose.yml:65–66`, `docker-compose.yml:80`  
**Severity:** BLOCKING — Credential Exposure

The development `docker-compose.yml` (committed to the repository) contains:

```yaml
- SECRET_KEY=supersecretkey
- X_INTROSPECT_SECRET=Kjs#idjXw
- SMTP_PASSWORD=orls draa fbxo neox   # Google App Password — live credential
- POSTGRES_PASSWORD=fleetpass
```

The SMTP password (`orls draa fbxo neox`) is an active Google App Password for `dheerajkumarp777@gmail.com`. Anyone with read access to this repo can send email from that account. The `docker-compose_prod.yaml` repeats the same pattern.

**Required Fix:**
- Rotate the SMTP password immediately.
- Remove all secret values from docker-compose files. Use `env_file: .env` referencing a file excluded from git.
- Add `.env` and `service.prod.env` to `.gitignore` (both currently appear absent from `.gitignore` based on the files present).
- Adopt Docker Swarm secrets or Kubernetes Secrets / HashiCorp Vault for production.

---

### PG-002 — Database Credentials Default to Trivial Values

**Files:** `app/config.py:11–12`, `docker-compose.yml:57–58`

`POSTGRES_PASSWORD` defaults to `"fleetpass"` in `Settings`. The docker-compose also sets the Postgres container password to `fleetpass`. If `DATABASE_URL` is not explicitly overridden in production, the app uses predictable credentials.

**Required Fix:** Remove defaults for `POSTGRES_PASSWORD`, `POSTGRES_USER`, and `DATABASE_URL`. Enforce required fields via Pydantic validator that raises `ValueError` on blank values.

---

### PG-003 — JWT Secret Key Has Trivial Default

**File:** `app/config.py:94`  
Cross-reference: `audit_report.md` AUDIT-002.

`SECRET_KEY` defaults to `"supersecretkey"`. All JWTs are forgeable if this is not overridden. In `docker-compose.yml:65` it is explicitly set to the same trivial value.

**Required Fix:** Require `SECRET_KEY` via `@field_validator` with minimum 32-character enforcement. No default permitted.

---

### PG-004 — SMTP App Password Stored in Source-Controlled Compose File

**File:** `docker-compose_prod.yaml:34`

```yaml
- SMTP_PASSWORD=orls draa fbxo neox
```

This is a live credential. Even if it is rotated immediately, the git history will retain it permanently unless the repository history is rewritten.

**Required Fix:**
1. Rotate the credential immediately.
2. Run `git filter-repo --path docker-compose_prod.yaml --invert-paths` or equivalent history-scrub.
3. Force-push to remote after notifying all collaborators.

---

### PG-005 — Firebase Key Mounted from Local Filesystem at Fixed Path

**Files:** `docker-compose.yml:105`, `docker-compose_prod.yaml:60`

```yaml
- ./app/firebase/firebase_key.json:/app/app/firebase/firebase_key.json:ro
```

The Firebase service account key file is expected to exist on the host at `./app/firebase/firebase_key.json`. This key grants full Firebase Admin SDK access. If the host is compromised or the file is accidentally committed, all Firebase resources are exposed.

**Required Fix:** Inject the key as a base64-encoded environment variable and decode at startup, or use a secrets manager (GCP Secret Manager, AWS Secrets Manager). Never bind-mount secret files from the host filesystem.

---

## 2. BLOCKING — Auth & Access Control

### PG-006 — No Rate Limiting on Authentication Endpoints

**File:** `app/routes/auth_router.py`  
Cross-reference: `audit_report.md` AUDIT-032.

No rate limiting on `/auth/employee/login`, `/auth/employee/request-otp`, `/auth/employee/verify-otp`, or any driver/vendor equivalent. Brute-force and credential stuffing attacks are unrestricted.

**Required Fix:** Deploy `slowapi` (backed by Redis) with tiered limits:
- `/login`: 10 attempts / minute per IP
- `/request-otp`: 5 requests / 10 minutes per user identity
- `/verify-otp`: 3 attempts per OTP lifetime (already partially enforced; add IP-level cap)

---

### PG-007 — Prometheus `/metrics` Endpoint Is Public

**File:** `main.py:121`  
Cross-reference: `audit_report.md` AUDIT-020.

`/metrics` is exposed on the public application port (8000/8100). Prometheus metrics reveal request volume, error rates, latency percentiles, and in-progress request counts. This is reconnaissance information for attackers.

**Required Fix:** Either restrict `/metrics` to the internal network via nginx `allow`/`deny` directives, or add HTTP Basic Auth middleware:

```python
@app.get("/metrics-auth")
async def metrics_with_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not (credentials.username == settings.METRICS_USER and 
            secrets.compare_digest(credentials.password, settings.METRICS_PASSWORD)):
        raise HTTPException(status_code=401)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

---

### PG-008 — Development OTP Leaked in API Response on Misconfiguration

**File:** `app/routes/auth_router.py:922–925`  
Cross-reference: `audit_report.md` AUDIT-007.

If `ENV` defaults to `"development"` due to missing environment variable, the OTP value is returned in the HTTP response body. A misconfigured production pod silently bypasses OTP authentication entirely.

**Required Fix:** Remove `otp_dev` response field entirely. Use seed fixtures or integration test overrides instead.

---

## 3. BLOCKING — Infrastructure & Deployment

### PG-009 — Alembic Migration Runs Synchronously in Async Lifespan (Startup Blocker)

**File:** `main.py:79`  
Cross-reference: `audit_report.md` AUDIT-008.

`run_migrations()` blocks the async event loop during startup. In Kubernetes, this causes liveness probe failures on tables with large `ALTER TABLE` operations, triggering premature pod restarts mid-migration — leaving the schema in a partial state.

**Required Fix:**
1. In Kubernetes: run migrations as an `initContainer` or a pre-deployment Job, not in the application lifespan.
2. In compose: use a dedicated `migrate` service that runs `alembic upgrade head` and completes before `fleet_api` starts via `depends_on: condition: service_completed_successfully`.

---

### PG-010 — Multiple Replicas Will Attempt Concurrent Migrations

**File:** `main.py:41–63`

`run_migrations()` is called by every application replica at startup. With 2+ replicas starting simultaneously, concurrent `alembic upgrade head` runs will:
- Race on DDL lock acquisition
- Potentially apply the same migration twice (Alembic's `alembic_version` table provides some protection, but DDL race conditions can cause `LockNotAvailable` errors and partial rollbacks)

**Required Fix:** Migrations must be run by exactly one process — an init container, a CI step, or a migration job — not by the web server replicas.

---

### PG-011 — No Horizontal Scaling Strategy for Session State

**Files:** `app/middleware/error_tracking.py:21–26`, `app/utils/cache_manager.py`

`ErrorTracker` stores errors in a Python list in process memory. `CacheManager` uses a single Redis connection (not a connection pool designed for high concurrency). With multiple Gunicorn workers or multiple container replicas:
- Each worker has an independent `ErrorTracker` — the `/errors` endpoint returns a fraction of actual errors depending on which worker handles the request.
- Under load, `CacheManager`'s single synchronous Redis client becomes a bottleneck.

**Required Fix:**
- Move `ErrorTracker` to Redis (sorted set keyed by timestamp, capped at 1000 entries via `ZREMRANGEBYRANK`).
- Use `redis.ConnectionPool` shared across the process, not a per-instance `redis.Redis()` object.

---

### PG-012 — Gunicorn Worker Count and Type Not Configured

**Files:** `requirements.txt:4`, `start.sh` (not reviewed, but present)

`gunicorn==21.2.0` is installed but no `gunicorn.conf.py` was found in the workspace. If the app starts with `uvicorn` directly (as in `main.py:171`), only a single worker handles all requests. If Gunicorn is used, the default worker class (`sync`) is incompatible with FastAPI's async request handlers.

**Required Fix:** Add `gunicorn.conf.py`:
```python
bind = "0.0.0.0:8000"
workers = (2 * cpu_count()) + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
keepalive = 5
```

---

## 4. NON-BLOCKING (Should Fix Before Scale)

### PG-013 — Two Conflicting PostgreSQL Driver Packages Installed

**File:** `requirements.txt:1–2`

```
psycopg2-binary==2.9.9   # SQLAlchemy 1.x style
psycopg[binary]==3.1.18  # psycopg3 (newer async driver)
```

Both drivers are installed. SQLAlchemy 2.x uses `psycopg2` by default unless `DATABASE_URL` uses the `postgresql+psycopg` scheme. Having both wastes container image size and creates ambiguity about which driver is active.

**Required Fix:** Pick one. For a new async-capable deployment, migrate fully to `psycopg3` with `DATABASE_URL = postgresql+psycopg://...`. Until then, remove `psycopg[binary]` if it's not actively used.

---

### PG-014 — No Graceful Shutdown for In-Flight Requests

**File:** `main.py:96`

The lifespan's shutdown block only logs `"Application shutting down"`. There is no:
- Wait for in-flight DB transactions to complete
- Drain of the BackgroundTasks queue
- Redis connection pool teardown

Under Kubernetes rolling updates, this can cause mid-request `500` errors when the pod is SIGTERM'd.

**Required Fix:**
```python
async def lifespan(app: FastAPI):
    yield
    # Graceful shutdown: allow up to 30s for in-flight requests
    await asyncio.sleep(0)  # yield to event loop to let requests drain
    engine.dispose()
    logger.info("DB connections closed")
```
Set `terminationGracePeriodSeconds: 30` in the Kubernetes Deployment manifest.

---

## 5. BLOCKING — Observability & Logging

### PG-015 — Full Settings Object (Including Secrets) Logged at Startup

**File:** `main.py:35`  
Cross-reference: `audit_report.md` AUDIT-031.

```python
logger.info("🚀 Fleet Manager starting — env: %s", settings)
```

Pydantic `BaseSettings.__repr__` emits all field values. `SMTP_PASSWORD`, `TWILIO_AUTH_TOKEN`, `SECRET_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD` are all written to stdout on every startup. These will be captured by any log aggregation tool (Datadog, CloudWatch, Loki, etc.).

**Required Fix:**
```python
logger.info(
    "Fleet Manager starting — ENV=%s VERSION=%s DB=%s:%s/%s",
    settings.ENV, settings.APP_VERSION,
    settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB
)
```

---

### PG-016 — No Structured (JSON) Log Output for Log Aggregation

**File:** `app/core/logging_config.py`

All log output uses Python's default text formatter. In a containerized deployment, logs are collected by Fluentd/Vector/Filebeat and forwarded to Elasticsearch or a similar store. Text-formatted logs require fragile regex parsing for log level, timestamp, and trace ID extraction.

**Required Fix:** Add a JSON formatter for production:
```python
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        })
```
Use text formatter in development, JSON formatter in production (gated on `settings.ENV == "production"`).

---

## 6. NON-BLOCKING Observability

### PG-017 — No Request Correlation ID / Distributed Tracing

There is no `X-Request-ID` or `X-Trace-ID` header propagation. When a request triggers multiple downstream service calls (DB, Redis, Firebase, SMTP), there is no way to correlate all log lines for a single request in a log aggregation system.

**Suggested Fix:** Add middleware that generates/accepts `X-Request-ID`, attaches it to the logging context, and returns it in the response headers. FastAPI's `RequestTrackingMiddleware` (already registered) could be extended for this.

---

### PG-018 — No Application Health Check Endpoint

There is no `/health` or `/ready` endpoint beyond `/metrics`. Kubernetes liveness and readiness probes should target a dedicated health endpoint that:
1. Verifies DB connectivity (`SELECT 1`)
2. Verifies Redis connectivity (`PING`)
3. Returns `200 OK` with a JSON body: `{"status": "ok", "db": "ok", "redis": "ok"}`

The `/metrics` endpoint is currently used as a proxy, but it does not check downstream dependencies.

---

### PG-019 — No Alerting on Error Rate or Latency Thresholds

Prometheus metrics are collected but no alert rules (`PrometheusRule`) or Grafana dashboards have been defined. Without configured alerts, a spike in `5xx` errors will not page on-call engineers.

---

## 7. BLOCKING — Reliability & Resilience

### PG-020 — Voice and WhatsApp Notifications Are Stub Implementations

**File:** `app/services/notification_service.py:388, 414`  
Cross-reference: `audit_report.md` AUDIT-041.

Both handlers `return True` without sending any message. Alert notifications marked as `SENT` for these channels are silently undelivered. Operations teams relying on voice escalation during incidents will not receive alerts.

**Required Fix:** Either implement the channels using Twilio's Voice and WhatsApp APIs, or change the status to `PENDING`/`SKIPPED` and log a warning. Never mark a notification `SENT` without delivery confirmation.

---

### PG-021 — No Retry or Dead-Letter Queue for Failed Notifications

**File:** `app/services/notification_service.py`

Email and SMS notifications are sent synchronously in the request-response cycle with no retry mechanism beyond `EMAIL_RETRY_ATTEMPTS` (which is an in-process loop, not a durable queue). A transient SMTP failure causes the entire notification batch to fail silently.

**Required Fix:** Use a task queue (Celery + Redis, or RQ) for notification delivery. Failed tasks should enter a dead-letter queue with exponential backoff retry. Notification logs in the DB should record retry count and last error.

---

### PG-022 — No Circuit Breaker for Redis

**File:** `app/utils/cache_manager.py`

If Redis becomes unavailable, every cache operation raises an unhandled exception that is currently caught and swallowed via `print()`. While this allows the application to degrade gracefully, there is no circuit breaker to stop attempting Redis calls during an outage (which adds latency to every request).

**Required Fix:** Implement a circuit breaker pattern:
```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=30)
def cache_get(self, key: str):
    return self.redis_client.get(key)
```

---

### PG-023 — In-Memory Error Tracker Loses Data on Restart

**File:** `app/middleware/error_tracking.py:21–26`  
Cross-reference: `audit_report.md` AUDIT-030.

`ErrorTracker` stores up to 1000 errors in a Python list. All data is lost on container restart or process crash — exactly when you most need error history for post-incident analysis.

**Required Fix:** Persist errors to Redis with a TTL:
```python
self.redis.zadd("error_tracker", {json.dumps(error): timestamp})
self.redis.zremrangebyrank("error_tracker", 0, -1001)  # keep latest 1000
```

---

## 8. BLOCKING — Data Integrity

### PG-024 — Migration Race Condition: Multiple Alembic Heads Possible

**Files:** `migrations/versions/` (22 migration files)

Migrations `20260304_1200_merge_escort_password_and_ride_reviews.py` suggests a prior merge was needed. As the team adds parallel feature branches, diverging migration heads will cause `alembic upgrade head` to fail or apply in the wrong order. There is no CI step enforcing linear migration history.

**Required Fix:** Add a pre-commit hook that runs `alembic check` (verifies no pending migrations exist in the working tree that have not been applied to the latest DB state). Block merges that introduce a second `head`.

---

### PG-025 — No Backup / Point-in-Time Recovery Strategy

The `docker-compose.yml` mounts a named volume `postgres_data` without any backup configuration. For production:
- No `pg_dump` schedule is defined.
- No WAL archiving or streaming replication is configured.
- A single container failure means data loss.

**Required Fix:**
- Enable WAL-G or pgBackRest for continuous archiving to S3/GCS.
- Schedule daily logical backups with `pg_dump`.
- Test restore procedures quarterly.

---

### PG-026 — No Database Connection Limits Enforced at Application Layer

**File:** `app/database/session.py:10–18`

```python
pool_size=settings.DB_POOL_SIZE,    # default: 10
max_overflow=settings.DB_MAX_OVERFLOW,  # default: 20
```

With Gunicorn spawning `(2 * N_CPU) + 1` workers, each with a 10+20 connection pool, a 4-core host creates up to `9 * 30 = 270` connections to Postgres. Postgres's default `max_connections = 100` will be exhausted.

**Required Fix:**
- Deploy PgBouncer in transaction pooling mode between the app and Postgres.
- Reduce `DB_POOL_SIZE` to 2–5 when PgBouncer is in use.
- Set `max_connections = 200` in `postgresql.conf` and monitor `pg_stat_activity`.

---

## 9. NON-BLOCKING — Testing & CI

### PG-027 — No CI/CD Pipeline Definition Found

No `.github/workflows/` CI definition was found for:
- Running `pytest` on every PR
- Running `flake8`/`ruff` linting
- Building and pushing Docker images
- Running `alembic check` to verify migration consistency

### PG-028 — Test Coverage Unknown

`pytest.ini` exists but no coverage targets or thresholds are set. `pytest-cov` is installed but not configured to fail the build below a coverage threshold.

**Suggested Fix:**
```ini
# pytest.ini
[pytest]
addopts = --cov=app --cov-fail-under=70 --cov-report=term-missing
```

### PG-029 — Integration Tests Depend on Live External Services

The test suite (`tests/`) was not fully reviewed, but the pattern of `NotificationService` importing `EmailService`, `SMSService`, and Firebase SDK at module level means tests will attempt to connect to real services unless all are mocked. This makes tests non-deterministic in CI environments without external service credentials.

---

## Appendix: Priority Matrix

| ID | Issue | Effort | Impact | Priority |
|----|-------|--------|--------|----------|
| PG-001 | Plaintext secrets in docker-compose | Low | Critical | **P0** |
| PG-004 | Live SMTP password in prod compose | Low | Critical | **P0** |
| PG-008 | OTP in API response on misconfig | Low | Critical | **P0** |
| PG-003 | JWT secret trivial default | Low | Critical | **P0** |
| PG-006 | No rate limiting on auth | Medium | High | **P1** |
| PG-007 | /metrics unauthenticated | Low | High | **P1** |
| PG-009 | Sync migration in async lifespan | Medium | High | **P1** |
| PG-010 | Concurrent migration on multi-replica | Medium | High | **P1** |
| PG-015 | Secrets in startup logs | Low | High | **P1** |
| PG-020 | Voice/WhatsApp stub sends SENT | Low | Medium | **P1** |
| PG-026 | DB connection pool exhaustion | Medium | High | **P1** |
| PG-011 | In-memory state for multi-worker | High | Medium | **P2** |
| PG-012 | Gunicorn not configured | Low | High | **P2** |
| PG-016 | No JSON log output | Medium | Medium | **P2** |
| PG-021 | No retry queue for notifications | High | Medium | **P2** |
| PG-022 | No Redis circuit breaker | Medium | Low | **P3** |
| PG-017 | No request correlation ID | Medium | Medium | **P3** |
| PG-018 | No /health endpoint | Low | Medium | **P3** |
