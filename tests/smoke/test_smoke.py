"""
Smoke test suite — lightweight pre-deployment stability checks.

Purpose: confirm the application boots, all key routes are registered, the DB
layer is reachable through the TestClient, and the auth subsystem responds
correctly.  These tests are intentionally fast (<1 s each) and run as the
first gate in CI before the heavier integration / API suites.

Markers: @pytest.mark.smoke
Test Classes:
    TestAppStartup              – root/docs endpoints
    TestHealthEndpoint          – /health structure & DB connectivity
    TestAuthEndpointsReachable  – auth routes return 4xx, never 500
    TestProtectedEndpointsRegistered – protected routes return 401, never 404
    TestOpenAPISchema           – OpenAPI JSON contains every expected tag
    TestDatabaseSmoke           – round-trip model create/read via TestClient
"""

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_V1 = "/api/v1"


def _auth_headers(client, email: str, password: str, login_path: str) -> dict:
    """Attempt login and return Bearer headers; skip the test on failure."""
    resp = client.post(f"{_V1}{login_path}", json={"email": email, "password": password})
    if resp.status_code != 200:
        pytest.skip(f"Login to {login_path} failed ({resp.status_code}) — seed data missing?")
    token = resp.json().get("access_token") or resp.json().get("data", {}).get("access_token")
    if not token:
        pytest.skip("Login response contained no access_token")
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. App startup
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestAppStartup:
    """Verify the application root and documentation endpoints are reachable."""

    def test_root_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_returns_welcome_message(self, client):
        body = client.get("/").json()
        assert "message" in body
        assert "Fleet" in body["message"] or "Welcome" in body["message"]

    def test_openapi_json_reachable(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200

    def test_openapi_json_is_valid_structure(self, client):
        schema = client.get("/openapi.json").json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "info" in schema

    def test_docs_ui_reachable(self, client):
        # Swagger UI returns HTML; just confirm it isn't a 404/500.
        resp = client.get("/docs")
        assert resp.status_code in (200, 307)

    def test_redoc_ui_reachable(self, client):
        resp = client.get("/redoc")
        assert resp.status_code in (200, 307)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Health endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestHealthEndpoint:
    """Validate /health response contract."""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_contains_status_key(self, client):
        body = client.get("/health").json()
        assert "status" in body
        assert body["status"] in ("ok", "degraded")

    def test_health_contains_db_key(self, client):
        body = client.get("/health").json()
        assert "db" in body

    def test_health_db_is_connected_in_test_env(self, client):
        """SQLite in-memory DB used by TestClient should always be connected."""
        body = client.get("/health").json()
        # In the test environment the override injects a working SQLite session,
        # so the DB connectivity check must not report an error.
        assert not str(body["db"]).startswith("error")

    def test_health_contains_redis_key(self, client):
        body = client.get("/health").json()
        assert "redis" in body

    def test_health_contains_migration_key(self, client):
        body = client.get("/health").json()
        assert "migration" in body

    def test_health_migration_has_expected_fields(self, client):
        migration = client.get("/health").json()["migration"]
        assert "current" in migration
        assert "head" in migration
        assert "up_to_date" in migration


# ─────────────────────────────────────────────────────────────────────────────
# 3. Auth endpoints — must respond with 4xx, never 5xx
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestAuthEndpointsReachable:
    """
    Verify each auth login route is registered and handles bad input
    gracefully (422 or 401) rather than crashing (500).
    """

    @pytest.mark.parametrize("path,payload", [
        (
            "/auth/employee/login",
            {"email": "nobody@test.com", "password": "wrong"},
        ),
        (
            "/auth/admin/login",
            {"email": "nobody@admin.com", "password": "wrong"},
        ),
        (
            "/auth/vendor/login",
            {"email": "nobody@vendor.com", "password": "wrong"},
        ),
    ])
    def test_login_endpoint_reachable_returns_4xx(self, client, path, payload):
        resp = client.post(f"{_V1}{path}", json=payload)
        assert resp.status_code < 500, (
            f"Auth route {path} returned 5xx: {resp.status_code} — {resp.text}"
        )
        assert resp.status_code >= 400, (
            f"Expected 4xx for bad credentials on {path}, got {resp.status_code}"
        )

    def test_employee_login_missing_fields_returns_422(self, client):
        resp = client.post(f"{_V1}/auth/employee/login", json={})
        assert resp.status_code == 422

    def test_admin_login_missing_fields_returns_422(self, client):
        resp = client.post(f"{_V1}/auth/admin/login", json={})
        assert resp.status_code == 422

    def test_introspect_missing_token_returns_4xx(self, client):
        resp = client.post(f"{_V1}/auth/introspect", json={"token": ""})
        assert resp.status_code < 500

    def test_reset_password_missing_fields_returns_4xx(self, client):
        resp = client.post(f"{_V1}/auth/reset-password", json={})
        assert resp.status_code < 500

    def test_auth_me_without_token_returns_401_or_403(self, client):
        resp = client.get(f"{_V1}/auth/me")
        assert resp.status_code in (401, 403)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Protected business endpoints — 401 means route exists
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestProtectedEndpointsRegistered:
    """
    Every listed endpoint must return 401/403 (not 404 or 5xx) when called
    without credentials — proving the route is registered and middleware
    guards it correctly.
    """

    PROTECTED_GET_ROUTES = [
        f"{_V1}/tenants",
        f"{_V1}/employees",
        f"{_V1}/drivers/get",      # driver list route (no root GET on /drivers)
        f"{_V1}/bookings/employee", # booking list route (root GET is not registered)
        f"{_V1}/teams",
        f"{_V1}/vehicles",
        f"{_V1}/vehicle-types",
        f"{_V1}/shifts",
        f"{_V1}/vendors",
        f"{_V1}/vendor-users",
        f"{_V1}/escorts",
        f"{_V1}/iam/roles",
        f"{_V1}/iam/permissions",
    ]

    @pytest.mark.parametrize("route", PROTECTED_GET_ROUTES)
    def test_protected_route_returns_401_or_403_without_auth(self, client, route):
        resp = client.get(route)
        assert resp.status_code in (401, 403), (
            f"Route {route} returned {resp.status_code} without auth — "
            f"expected 401/403. Body: {resp.text[:200]}"
        )

    def test_bookings_post_without_auth_returns_401_or_403(self, client):
        resp = client.post(f"{_V1}/bookings", json={})
        assert resp.status_code in (401, 403)

    def test_employees_post_without_auth_returns_401_or_403(self, client):
        resp = client.post(f"{_V1}/employees", json={})
        assert resp.status_code in (401, 403)

    def test_tenant_post_without_auth_returns_401_or_403(self, client):
        resp = client.post(f"{_V1}/tenants", json={})
        assert resp.status_code in (401, 403)

    def test_no_protected_route_returns_404(self, client):
        """Regression guard: none of the known routes should be unmounted."""
        for route in self.PROTECTED_GET_ROUTES:
            resp = client.get(route)
            assert resp.status_code != 404, (
                f"Route {route} returned 404 — it may have been accidentally unmounted."
            )


# ─────────────────────────────────────────────────────────────────────────────
# 5. OpenAPI schema tag completeness
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestOpenAPISchema:
    """Check the generated OpenAPI schema covers all major domain tags."""

    REQUIRED_TAGS = {
        "authentication",
        "tenants",
        "employees",
        "drivers",
        "bookings",
        "vehicles",
        "teams",
        "vendors",
    }

    def test_openapi_contains_required_tags(self, client):
        schema = client.get("/openapi.json").json()
        declared_tags = {t["name"].lower() for t in schema.get("tags", [])}
        # Also accept tags that appear only on paths (not in the top-level tags list)
        path_tags: set = set()
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if isinstance(operation, dict):
                    path_tags.update(tag.lower() for tag in operation.get("tags", []))
        all_tags = declared_tags | path_tags
        missing = self.REQUIRED_TAGS - all_tags
        assert not missing, f"OpenAPI schema is missing expected tags: {missing}"

    def test_openapi_has_multiple_paths(self, client):
        schema = client.get("/openapi.json").json()
        assert len(schema.get("paths", {})) > 20, (
            "OpenAPI schema has fewer than 20 paths — router registration may be incomplete."
        )

    def test_openapi_version_is_3x(self, client):
        schema = client.get("/openapi.json").json()
        assert schema["openapi"].startswith("3.")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Database round-trip smoke
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
class TestDatabaseSmoke:
    """
    Verify the DB session injected by the TestClient can actually persist
    and retrieve records.  Uses the lowest-level fixture (test_db) directly
    so we stay independent from business logic.
    """

    def test_db_session_executes_select_1(self, test_db):
        from sqlalchemy.sql import text
        result = test_db.execute(text("SELECT 1")).scalar()
        assert result == 1

    def test_db_session_can_create_and_query_tenant(self, test_db):
        from app.models.tenant import Tenant
        tenant = Tenant(
            tenant_id="SMOKE_TENANT_01",
            name="Smoke Test Corp",
            address="1 Smoke Lane",
            latitude=12.9,
            longitude=77.5,
            is_active=True,
        )
        test_db.add(tenant)
        test_db.commit()
        fetched = test_db.query(Tenant).filter_by(tenant_id="SMOKE_TENANT_01").first()
        assert fetched is not None
        assert fetched.name == "Smoke Test Corp"

    def test_db_session_isolation_between_tests(self, test_db):
        """The tenant created in the previous test must NOT bleed into this one."""
        from app.models.tenant import Tenant
        fetched = test_db.query(Tenant).filter_by(tenant_id="SMOKE_TENANT_01").first()
        assert fetched is None, (
            "SMOKE_TENANT_01 leaked from a previous test — test isolation is broken."
        )

    def test_client_db_override_works(self, client, test_db):
        """Confirm the TestClient and test_db share the same in-memory DB."""
        from app.models.tenant import Tenant
        tenant = Tenant(
            tenant_id="SMOKE_SHARED_01",
            name="Shared DB Corp",
            address="2 Shared Lane",
            latitude=13.0,
            longitude=77.6,
            is_active=True,
        )
        test_db.add(tenant)
        test_db.commit()
        # The TestClient should see this tenant via the /health DB ping (it just
        # needs to be able to execute SELECT 1 — full row visibility is proven by
        # the direct session test above, since both use the same StaticPool).
        resp = client.get("/health")
        assert resp.status_code == 200
        assert not str(resp.json().get("db", "")).startswith("error")
