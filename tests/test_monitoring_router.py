"""
Tests for Monitoring Router — all 15 unauthenticated observability endpoints.

Routes covered
──────────────
Health / metrics
  GET /api/v1/monitoring/health
  GET /api/v1/monitoring/database/metrics
  GET /api/v1/monitoring/cache/stats
  GET /api/v1/monitoring/system/info
  GET /api/v1/monitoring/tasks/{task_id}

Error tracking
  GET /api/v1/monitoring/errors/recent
  GET /api/v1/monitoring/errors/stats
  GET /api/v1/monitoring/errors/by-type/{error_type}
  GET /api/v1/monitoring/errors/by-path

Request tracking
  GET /api/v1/monitoring/requests/recent
  GET /api/v1/monitoring/requests/stats
  GET /api/v1/monitoring/requests/slow
  GET /api/v1/monitoring/requests/errors
  GET /api/v1/monitoring/requests/by-path

Dashboard
  GET /api/v1/monitoring/dashboard

Notes
─────
app/routes/__init__.py re-exports `router as monitoring_router`, so the name
"app.routes.monitoring_router" resolves to the APIRouter object — NOT the
module — when used as a dotted patch string.  We therefore resolve the real
module via sys.modules after a forced importlib.import_module() call.
"""

import sys
import importlib

import pytest
from unittest.mock import patch, MagicMock

# ── Module/object references ──────────────────────────────────────────────────
importlib.import_module("app.routes.monitoring_router")
importlib.import_module("app.middleware.error_tracking")
importlib.import_module("app.middleware.request_tracking")

_mon = sys.modules["app.routes.monitoring_router"]          # the real module
_et  = sys.modules["app.middleware.error_tracking"].error_tracker
_rt  = sys.modules["app.middleware.request_tracking"].request_tracker

BASE = "/api/v1/monitoring"

# ─────────────────────────────────────────────────────────────────────────────
# Shared mock return values
# ─────────────────────────────────────────────────────────────────────────────

_DB_HEALTH = {
    "status": "healthy",
    "timestamp": "2024-01-01T00:00:00",
    "connections": {"active": 5, "idle": 3},
}
_CACHE_HEALTH  = {"status": "healthy", "memory_used": "10MB"}
_DB_METRICS    = {"query_count": 100, "avg_query_time_ms": 5.2}
_ERROR_LIST    = [{"type": "ValueError", "message": "bad", "path": "/api/v1/booking"}]
_ERROR_STATS   = {"total": 1, "by_type": {"ValueError": 1}}
_REQUEST_LIST  = [{"method": "GET", "path": "/api/v1/booking", "status_code": 200}]
_REQUEST_STATS = {
    "total": 500,
    "error_rate": 0.02,
    "avg_response_time_ms": 50,
    "requests_per_minute": 12,
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET /monitoring/health
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_all_systems_healthy(self, client):
        with (
            patch.object(_mon, "get_connection_health", return_value=_DB_HEALTH),
            patch.object(_mon, "get_cache_stats", return_value=_CACHE_HEALTH),
        ):
            r = client.get(f"{BASE}/health")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["data"]["status"] == "healthy"
        assert body["data"]["database"]["status"] == "healthy"

    def test_health_degraded_when_db_unhealthy(self, client):
        db_down = {**_DB_HEALTH, "status": "unhealthy"}
        with (
            patch.object(_mon, "get_connection_health", return_value=db_down),
            patch.object(_mon, "get_cache_stats", return_value=_CACHE_HEALTH),
        ):
            r = client.get(f"{BASE}/health")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "degraded"

    def test_health_degraded_when_cache_unhealthy(self, client):
        cache_down = {**_CACHE_HEALTH, "status": "unhealthy"}
        with (
            patch.object(_mon, "get_connection_health", return_value=_DB_HEALTH),
            patch.object(_mon, "get_cache_stats", return_value=cache_down),
        ):
            r = client.get(f"{BASE}/health")
        assert r.json()["data"]["status"] == "degraded"

    def test_health_503_on_exception(self, client):
        with patch.object(_mon, "get_connection_health", side_effect=Exception("DB down")):
            r = client.get(f"{BASE}/health")
        assert r.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET /monitoring/database/metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestDatabaseMetrics:
    def test_get_db_metrics_success(self, client):
        with patch.object(_mon, "get_db_metrics", return_value=_DB_METRICS):
            r = client.get(f"{BASE}/database/metrics")
        assert r.status_code == 200
        assert r.json()["data"]["query_count"] == 100

    def test_get_db_metrics_500_on_exception(self, client):
        with patch.object(_mon, "get_db_metrics", side_effect=Exception("unavailable")):
            r = client.get(f"{BASE}/database/metrics")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET /monitoring/cache/stats
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheStats:
    def test_get_cache_stats_success(self, client):
        with patch.object(_mon, "get_cache_stats", return_value=_CACHE_HEALTH):
            r = client.get(f"{BASE}/cache/stats")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "healthy"

    def test_get_cache_stats_500_on_exception(self, client):
        with patch.object(_mon, "get_cache_stats", side_effect=RuntimeError("Redis timeout")):
            r = client.get(f"{BASE}/cache/stats")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 4. GET /monitoring/system/info
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemInfo:
    @staticmethod
    def _make_mem():
        m = MagicMock()
        m.total    = 8 * 1024 ** 3
        m.available = 4 * 1024 ** 3
        m.percent  = 50.0
        return m

    @staticmethod
    def _make_disk():
        d = MagicMock()
        d.total   = 100 * 1024 ** 3
        d.free    = 60  * 1024 ** 3
        d.percent = 40.0
        return d

    def test_system_info_success(self, client):
        with (
            patch("psutil.cpu_percent",    return_value=25.0),
            patch("psutil.virtual_memory", return_value=self._make_mem()),
            patch("psutil.disk_usage",     return_value=self._make_disk()),
        ):
            r = client.get(f"{BASE}/system/info")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "cpu_usage"  in data
        assert "memory"     in data
        assert "disk"       in data
        assert "platform"   in data

    def test_system_info_500_on_exception(self, client):
        with patch("psutil.cpu_percent", side_effect=Exception("psutil error")):
            r = client.get(f"{BASE}/system/info")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 5. GET /monitoring/tasks/{task_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskStatus:
    def test_get_existing_task(self, client):
        task_info = {"task_id": "abc123", "status": "completed", "result": "ok"}
        with patch("app.utils.task_manager.get_task_status", return_value=task_info):
            r = client.get(f"{BASE}/tasks/abc123")
        assert r.status_code == 200
        assert r.json()["data"]["task_id"] == "abc123"

    def test_get_nonexistent_task_404(self, client):
        with patch("app.utils.task_manager.get_task_status", return_value=None):
            r = client.get(f"{BASE}/tasks/does-not-exist")
        assert r.status_code == 404

    def test_get_task_500_on_exception(self, client):
        with patch(
            "app.utils.task_manager.get_task_status",
            side_effect=Exception("store unavailable"),
        ):
            r = client.get(f"{BASE}/tasks/boom")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 6. GET /monitoring/errors/recent
# ─────────────────────────────────────────────────────────────────────────────

class TestRecentErrors:
    def test_returns_error_list(self, client):
        with patch.object(_et, "get_recent_errors", return_value=_ERROR_LIST):
            r = client.get(f"{BASE}/errors/recent")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_limit_query_param_accepted(self, client):
        with patch.object(_et, "get_recent_errors", return_value=[]):
            r = client.get(f"{BASE}/errors/recent?limit=10")
        assert r.status_code == 200

    def test_limit_below_minimum_rejected(self, client):
        r = client.get(f"{BASE}/errors/recent?limit=0")
        assert r.status_code == 422

    def test_limit_above_maximum_rejected(self, client):
        r = client.get(f"{BASE}/errors/recent?limit=501")
        assert r.status_code == 422

    def test_500_on_exception(self, client):
        with patch.object(_et, "get_recent_errors", side_effect=Exception("store error")):
            r = client.get(f"{BASE}/errors/recent")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 7. GET /monitoring/errors/stats
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorStats:
    def test_returns_stats(self, client):
        with patch.object(_et, "get_error_stats", return_value=_ERROR_STATS):
            r = client.get(f"{BASE}/errors/stats")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_500_on_exception(self, client):
        with patch.object(_et, "get_error_stats", side_effect=Exception("stats unavailable")):
            r = client.get(f"{BASE}/errors/stats")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 8. GET /monitoring/errors/by-type/{error_type}
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorsByType:
    def test_returns_errors_for_type(self, client):
        with patch.object(_et, "get_errors_by_type", return_value=_ERROR_LIST):
            r = client.get(f"{BASE}/errors/by-type/ValueError")
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["error_type"] == "ValueError"
        assert body["total"] == 1

    def test_empty_list_for_unknown_type(self, client):
        with patch.object(_et, "get_errors_by_type", return_value=[]):
            r = client.get(f"{BASE}/errors/by-type/NoSuchError")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_500_on_exception(self, client):
        with patch.object(_et, "get_errors_by_type", side_effect=Exception("error")):
            r = client.get(f"{BASE}/errors/by-type/Any")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 9. GET /monitoring/errors/by-path
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorsByPath:
    def test_returns_errors_for_path(self, client):
        with patch.object(_et, "get_errors_by_path", return_value=_ERROR_LIST):
            r = client.get(f"{BASE}/errors/by-path?path=/api/v1/booking")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_missing_path_param_rejected(self, client):
        r = client.get(f"{BASE}/errors/by-path")
        assert r.status_code == 422

    def test_500_on_exception(self, client):
        with patch.object(_et, "get_errors_by_path", side_effect=Exception("error")):
            r = client.get(f"{BASE}/errors/by-path?path=/some/path")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 10. GET /monitoring/requests/recent
# ─────────────────────────────────────────────────────────────────────────────

class TestRecentRequests:
    def test_returns_request_list(self, client):
        with patch.object(_rt, "get_recent_requests", return_value=_REQUEST_LIST):
            r = client.get(f"{BASE}/requests/recent")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_limit_param_accepted(self, client):
        with patch.object(_rt, "get_recent_requests", return_value=[]):
            r = client.get(f"{BASE}/requests/recent?limit=200")
        assert r.status_code == 200

    def test_limit_zero_rejected(self, client):
        r = client.get(f"{BASE}/requests/recent?limit=0")
        assert r.status_code == 422

    def test_limit_over_max_rejected(self, client):
        r = client.get(f"{BASE}/requests/recent?limit=1001")
        assert r.status_code == 422

    def test_500_on_exception(self, client):
        with patch.object(_rt, "get_recent_requests", side_effect=Exception("tracker down")):
            r = client.get(f"{BASE}/requests/recent")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 11. GET /monitoring/requests/stats
# ─────────────────────────────────────────────────────────────────────────────

class TestRequestStats:
    def test_returns_stats(self, client):
        with patch.object(_rt, "get_request_stats", return_value=_REQUEST_STATS):
            r = client.get(f"{BASE}/requests/stats")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 500

    def test_500_on_exception(self, client):
        with patch.object(_rt, "get_request_stats", side_effect=Exception("stats error")):
            r = client.get(f"{BASE}/requests/stats")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 12. GET /monitoring/requests/slow
# ─────────────────────────────────────────────────────────────────────────────

class TestSlowRequests:
    def test_returns_slow_requests(self, client):
        with patch.object(_rt, "get_slow_requests", return_value=_REQUEST_LIST):
            r = client.get(f"{BASE}/requests/slow")
        assert r.status_code == 200
        body = r.json()["data"]
        assert "threshold_ms" in body
        assert body["total"] == 1

    def test_custom_threshold(self, client):
        with patch.object(_rt, "get_slow_requests", return_value=[]):
            r = client.get(f"{BASE}/requests/slow?threshold_ms=500")
        assert r.status_code == 200
        assert r.json()["data"]["threshold_ms"] == 500

    def test_threshold_below_minimum_rejected(self, client):
        r = client.get(f"{BASE}/requests/slow?threshold_ms=50")
        assert r.status_code == 422

    def test_500_on_exception(self, client):
        with patch.object(_rt, "get_slow_requests", side_effect=Exception("error")):
            r = client.get(f"{BASE}/requests/slow")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 13. GET /monitoring/requests/errors
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorRequests:
    def test_returns_error_requests(self, client):
        with patch.object(_rt, "get_error_requests", return_value=_REQUEST_LIST):
            r = client.get(f"{BASE}/requests/errors")
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 1

    def test_limit_param(self, client):
        with patch.object(_rt, "get_error_requests", return_value=[]):
            r = client.get(f"{BASE}/requests/errors?limit=25")
        assert r.status_code == 200

    def test_500_on_exception(self, client):
        with patch.object(_rt, "get_error_requests", side_effect=Exception("tracker error")):
            r = client.get(f"{BASE}/requests/errors")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 14. GET /monitoring/requests/by-path
# ─────────────────────────────────────────────────────────────────────────────

class TestRequestsByPath:
    def test_returns_requests_for_path(self, client):
        with patch.object(_rt, "get_requests_by_path", return_value=_REQUEST_LIST):
            r = client.get(f"{BASE}/requests/by-path?path=/api/v1/booking")
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["total"] == 1
        assert body["path"] == "/api/v1/booking"

    def test_missing_path_param_rejected(self, client):
        r = client.get(f"{BASE}/requests/by-path")
        assert r.status_code == 422

    def test_500_on_exception(self, client):
        with patch.object(_rt, "get_requests_by_path", side_effect=Exception("error")):
            r = client.get(f"{BASE}/requests/by-path?path=/any")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# 15. GET /monitoring/dashboard
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboard:
    def test_dashboard_success(self, client):
        patches = [
            patch.object(_mon, "get_connection_health", return_value=_DB_HEALTH),
            patch.object(_mon, "get_cache_stats",       return_value=_CACHE_HEALTH),
            patch.object(_mon, "get_db_metrics",        return_value=_DB_METRICS),
            patch.object(_et,  "get_error_stats",       return_value=_ERROR_STATS),
            patch.object(_et,  "get_recent_errors",     return_value=_ERROR_LIST),
            patch.object(_rt,  "get_request_stats",     return_value=_REQUEST_STATS),
            patch.object(_rt,  "get_error_requests",    return_value=[]),
            patch.object(_rt,  "get_slow_requests",     return_value=[]),
        ]
        for p in patches:
            p.start()
        try:
            r = client.get(f"{BASE}/dashboard")
        finally:
            for p in patches:
                p.stop()

        assert r.status_code == 200
        data = r.json()["data"]
        assert "health"            in data
        assert "database_metrics"  in data
        assert "cache_stats"       in data
        assert "errors"            in data
        assert "requests"          in data

    def test_dashboard_500_on_partial_failure(self, client):
        """If any dependency throws, the whole dashboard returns 500."""
        with patch.object(_mon, "get_connection_health", side_effect=Exception("db down")):
            r = client.get(f"{BASE}/dashboard")
        assert r.status_code == 500
