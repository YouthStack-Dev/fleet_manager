"""
Fleet Manager — Locust Performance Test Suite
==============================================

Purpose
-------
Simulate realistic mixed-workload traffic against a **running** Fleet Manager
instance to measure throughput, latency percentiles, and error rates under load.

NOT a pytest test — run with Locust directly:

    # Headless (CI):
    locust -f tests/performance/locustfile.py \\
           --headless \\
           --users 50 \\
           --spawn-rate 5 \\
           --run-time 2m \\
           --host http://localhost:8000 \\
           --csv=reports/perf_results

    # Interactive web UI:
    locust -f tests/performance/locustfile.py --host http://localhost:8000

Environment variables (all optional — fall back to dev-seed defaults):
    FLEET_ADMIN_EMAIL      Email of a seeded admin user
    FLEET_ADMIN_PASSWORD   Password of the admin user
    FLEET_EMPLOYEE_EMAIL   Email of a seeded employee
    FLEET_EMPLOYEE_PASSWORD Password of the employee
    FLEET_TENANT_ID        Tenant ID to scope list queries

User classes
------------
AdminUser   (weight=1) — admin-heavy: tenant management, employee listing,
                          reporting, route management
EmployeeUser (weight=3) — employee-heavy: booking CRUD, profile reads,
                          announcement listing (realistic prod ratio)
UnauthenticatedUser (weight=1) — probe auth endpoints and public routes only
"""

import os
import json
import random
import string
from datetime import date, timedelta
from typing import Optional

from locust import HttpUser, TaskSet, task, between, events, constant_pacing

# ─── Configuration ────────────────────────────────────────────────────────────

V1 = "/api/v1"

ADMIN_EMAIL    = os.getenv("FLEET_ADMIN_EMAIL",    "admin@fleetmanager.com")
ADMIN_PASSWORD = os.getenv("FLEET_ADMIN_PASSWORD", "Admin@123")

EMPLOYEE_EMAIL    = os.getenv("FLEET_EMPLOYEE_EMAIL",    "employee@test.com")
EMPLOYEE_PASSWORD = os.getenv("FLEET_EMPLOYEE_PASSWORD", "Employee@123")

TENANT_ID = os.getenv("FLEET_TENANT_ID", "")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _rand_str(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


def _future_date(days_ahead: int = 1) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Task Sets ────────────────────────────────────────────────────────────────

class AdminTasks(TaskSet):
    """
    Represents an admin user session.

    Lifecycle:
      on_start  → POST /auth/admin/login  → store token
      tasks     → weighted mix of read & write operations
      on_stop   → (no-op; token expires naturally)
    """

    token: Optional[str] = None

    def on_start(self):
        with self.client.post(
            f"{V1}/auth/admin/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            catch_response=True,
            name="[admin] login",
        ) as resp:
            if resp.status_code == 200:
                body = resp.json()
                # Support both {"access_token": ...} and {"data": {"access_token": ...}}
                self.token = (
                    body.get("access_token")
                    or (body.get("data") or {}).get("access_token")
                )
                if not self.token:
                    resp.failure("Login succeeded but no access_token in response")
            else:
                resp.failure(f"Admin login failed: {resp.status_code}")

    # ── Read-heavy (weight 3) ─────────────────────────────────────────────────

    @task(3)
    def list_tenants(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/tenants",
            headers=_auth_headers(self.token),
            name="[admin] list tenants",
        )

    @task(3)
    def list_employees(self):
        if not self.token:
            return
        params = {}
        if TENANT_ID:
            params["tenant_id"] = TENANT_ID
        self.client.get(
            f"{V1}/employees",
            headers=_auth_headers(self.token),
            params=params,
            name="[admin] list employees",
        )

    @task(2)
    def list_drivers(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/drivers",
            headers=_auth_headers(self.token),
            name="[admin] list drivers",
        )

    @task(2)
    def list_vehicles(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/vehicles",
            headers=_auth_headers(self.token),
            name="[admin] list vehicles",
        )

    @task(2)
    def list_routes(self):
        if not self.token:
            return
        params = {}
        if TENANT_ID:
            params["tenant_id"] = TENANT_ID
        self.client.get(
            f"{V1}/route-management",
            headers=_auth_headers(self.token),
            params=params,
            name="[admin] list routes",
        )

    @task(1)
    def list_vendors(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/vendors",
            headers=_auth_headers(self.token),
            name="[admin] list vendors",
        )

    @task(1)
    def list_iam_roles(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/iam/roles",
            headers=_auth_headers(self.token),
            name="[admin] list IAM roles",
        )

    @task(1)
    def list_bookings(self):
        if not self.token:
            return
        params = {}
        if TENANT_ID:
            params["tenant_id"] = TENANT_ID
        self.client.get(
            f"{V1}/bookings",
            headers=_auth_headers(self.token),
            params=params,
            name="[admin] list bookings",
        )

    # ── Write (weight 1) ──────────────────────────────────────────────────────

    @task(1)
    def create_and_delete_vehicle_type(self):
        """Create a vehicle type then immediately delete it to avoid data buildup."""
        if not self.token:
            return
        name = f"perf_vtype_{_rand_str()}"
        with self.client.post(
            f"{V1}/vehicle-types",
            json={"name": name, "description": "Locust perf test type"},
            headers=_auth_headers(self.token),
            catch_response=True,
            name="[admin] create vehicle-type",
        ) as resp:
            if resp.status_code in (200, 201):
                vt_id = (resp.json().get("data") or resp.json()).get("vehicle_type_id")
                if vt_id:
                    self.client.delete(
                        f"{V1}/vehicle-types/{vt_id}",
                        headers=_auth_headers(self.token),
                        name="[admin] delete vehicle-type",
                    )
            else:
                resp.failure(f"Create vehicle-type returned {resp.status_code}")


class EmployeeTasks(TaskSet):
    """
    Represents an employee / end-user session.

    Lifecycle:
      on_start  → POST /auth/employee/login → store token
      tasks     → booking reads, profile check, announcement listing
    """

    token: Optional[str] = None
    booking_ids: list

    def on_start(self):
        self.booking_ids = []
        with self.client.post(
            f"{V1}/auth/employee/login",
            json={"email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PASSWORD},
            catch_response=True,
            name="[employee] login",
        ) as resp:
            if resp.status_code == 200:
                body = resp.json()
                self.token = (
                    body.get("access_token")
                    or (body.get("data") or {}).get("access_token")
                )
                if not self.token:
                    resp.failure("Login succeeded but no access_token in response")
            else:
                resp.failure(f"Employee login failed: {resp.status_code}")

    # ── Profile (weight 3) ────────────────────────────────────────────────────

    @task(3)
    def get_my_profile(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/auth/me",
            headers=_auth_headers(self.token),
            name="[employee] GET /auth/me",
        )

    # ── Bookings (weight 4) ───────────────────────────────────────────────────

    @task(4)
    def list_my_bookings(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/bookings",
            headers=_auth_headers(self.token),
            name="[employee] list bookings",
        )

    @task(2)
    def create_booking(self):
        """
        Create a one-way booking for tomorrow; store ID for the get_booking task.
        Uses a randomised pickup address to avoid exact-duplicate errors.
        """
        if not self.token:
            return
        tomorrow = _future_date(1)
        payload = {
            "booking_dates": [tomorrow],
            "booking_type": "pickup",
            "pickup_address": f"{random.randint(1, 999)} Locust Lane, Bengaluru",
            "pickup_latitude": round(12.9716 + random.uniform(-0.05, 0.05), 6),
            "pickup_longitude": round(77.5946 + random.uniform(-0.05, 0.05), 6),
        }
        with self.client.post(
            f"{V1}/bookings",
            json=payload,
            headers=_auth_headers(self.token),
            catch_response=True,
            name="[employee] create booking",
        ) as resp:
            if resp.status_code in (200, 201):
                data = resp.json().get("data") or resp.json()
                bid = data.get("booking_id") or data.get("id")
                if bid:
                    self.booking_ids.append(bid)
            # 422 is expected when required fields are missing in some variants;
            # don't fail the task for validation errors.
            elif resp.status_code not in (422,):
                resp.failure(f"Create booking returned {resp.status_code}")

    @task(3)
    def get_booking_detail(self):
        if not self.token or not self.booking_ids:
            return
        bid = random.choice(self.booking_ids)
        self.client.get(
            f"{V1}/bookings/{bid}",
            headers=_auth_headers(self.token),
            name="[employee] GET booking/:id",
        )

    # ── Announcements (weight 1) ──────────────────────────────────────────────

    @task(1)
    def list_announcements(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/announcements",
            headers=_auth_headers(self.token),
            name="[employee] list announcements",
        )

    # ── Shifts / teams (weight 1) ─────────────────────────────────────────────

    @task(1)
    def list_shifts(self):
        if not self.token:
            return
        self.client.get(
            f"{V1}/shifts",
            headers=_auth_headers(self.token),
            name="[employee] list shifts",
        )


class UnauthenticatedTasks(TaskSet):
    """
    Simulate anonymous probing — health checks, root, bad auth attempts.
    Measures baseline overhead of the middleware stack without DB auth.
    """

    @task(5)
    def health_check(self):
        self.client.get("/health", name="[unauth] GET /health")

    @task(3)
    def root(self):
        self.client.get("/", name="[unauth] GET /")

    @task(1)
    def bad_employee_login(self):
        self.client.post(
            f"{V1}/auth/employee/login",
            json={"email": "nobody@test.com", "password": "wrong"},
            name="[unauth] bad employee login → 401",
        )

    @task(1)
    def bad_admin_login(self):
        self.client.post(
            f"{V1}/auth/admin/login",
            json={"email": "nobody@admin.com", "password": "wrong"},
            name="[unauth] bad admin login → 401",
        )

    @task(1)
    def missing_auth_on_employees(self):
        """Confirms middleware correctly rejects unauthenticated requests."""
        with self.client.get(
            f"{V1}/employees",
            catch_response=True,
            name="[unauth] /employees → 401",
        ) as resp:
            if resp.status_code in (401, 403):
                resp.success()
            else:
                resp.failure(f"Expected 401/403, got {resp.status_code}")


# ─── User Classes ─────────────────────────────────────────────────────────────

class AdminUser(HttpUser):
    """
    Represents an admin power user.

    Wait strategy: 1–3 s between tasks (realistic think time for a UI-driven user).
    Weight: 1 (1 admin for every 3 employees in the simulated population).
    """

    tasks = [AdminTasks]
    wait_time = between(1, 3)
    weight = 1


class EmployeeUser(HttpUser):
    """
    Represents a regular employee using the employee app.

    Wait strategy: 0.5–2 s (mobile app, fast interactions).
    Weight: 3 (most users in the system are employees).
    """

    tasks = [EmployeeTasks]
    wait_time = between(0.5, 2)
    weight = 3


class UnauthenticatedUser(HttpUser):
    """
    Represents monitoring probes, bots, or misconfigured clients.

    Weight: 1.
    """

    tasks = [UnauthenticatedTasks]
    wait_time = between(0.2, 1)
    weight = 1


# ─── Custom Locust events (optional CI pass/fail thresholds) ──────────────────

@events.quitting.add_listener
def _assert_thresholds(environment, **kwargs):
    """
    Fail the Locust run (exit code 1) if any SLA is breached.
    These thresholds are intentionally conservative; tighten per team agreement.

    Thresholds:
      - Overall error rate  < 1 %
      - p95 response time   < 2 000 ms
      - p99 response time   < 5 000 ms
    """
    stats = environment.stats

    total_requests = stats.total.num_requests
    total_failures = stats.total.num_failures
    if total_requests == 0:
        return  # No data — nothing to assert.

    error_rate = total_failures / total_requests
    p95 = stats.total.get_response_time_percentile(0.95)
    p99 = stats.total.get_response_time_percentile(0.99)

    breaches = []
    if error_rate >= 0.01:
        breaches.append(
            f"Error rate {error_rate:.2%} >= 1% threshold "
            f"({total_failures}/{total_requests} failures)"
        )
    if p95 is not None and p95 > 2000:
        breaches.append(f"p95 latency {p95:.0f}ms > 2000ms threshold")
    if p99 is not None and p99 > 5000:
        breaches.append(f"p99 latency {p99:.0f}ms > 5000ms threshold")

    if breaches:
        print("\n[PERF] SLA BREACH DETECTED:")
        for b in breaches:
            print(f"  ✗  {b}")
        environment.process_exit_code = 1
    else:
        print(
            f"\n[PERF] SLA OK — error_rate={error_rate:.2%}, "
            f"p95={p95:.0f}ms, p99={p99:.0f}ms"
        )
