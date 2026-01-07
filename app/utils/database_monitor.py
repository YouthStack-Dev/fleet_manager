"""
Database monitoring utilities for Fleet Manager
Tracks connection pools, slow queries, and performance metrics
"""
import time
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import event, text

# India Standard Time
IST = ZoneInfo("Asia/Kolkata")
from sqlalchemy.engine import Engine
from app.database.session import get_db
from app.utils.cache_manager import cache
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class DatabaseMonitor:
    """Monitors database performance and connection pools"""

    def __init__(self):
        self.query_log = []
        self.connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "idle_connections": 0,
            "pool_overflow": 0
        }
        self.slow_query_threshold = 1.0  # seconds

    def setup_monitoring(self, engine: Engine):
        """Setup SQLAlchemy event listeners for monitoring"""

        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault('query_start_time', []).append(time.time())

        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total_time = time.time() - conn.info['query_start_time'].pop()

            # Log slow queries
            if total_time > self.slow_query_threshold:
                query_info = {
                    "timestamp": datetime.now(IST).isoformat(),
                    "query": statement[:500],  # Truncate long queries
                    "duration": total_time,
                    "parameters": str(parameters)[:200] if parameters else None
                }
                self.query_log.append(query_info)

                # Keep only last 100 slow queries
                if len(self.query_log) > 100:
                    self.query_log.pop(0)

                logger.warning(f"Slow query detected: {total_time:.2f}s - {statement[:100]}...")

        @event.listens_for(engine, "connect")
        def connect(dbapi_connection, connection_record):
            self.connection_stats["total_connections"] += 1

        @event.listens_for(engine, "checkout")
        def checkout(dbapi_connection, connection_record, connection_proxy):
            self.connection_stats["active_connections"] += 1

        @event.listens_for(engine, "checkin")
        def checkin(dbapi_connection, connection_record):
            self.connection_stats["active_connections"] -= 1
            self.connection_stats["idle_connections"] += 1

    def get_connection_stats(self) -> Dict:
        """Get current connection pool statistics"""
        return self.connection_stats.copy()

    def get_slow_queries(self, limit: int = 10) -> List[Dict]:
        """Get recent slow queries"""
        return self.query_log[-limit:]

    def get_performance_metrics(self) -> Dict:
        """Get comprehensive performance metrics"""
        # Get connection stats
        conn_stats = self.get_connection_stats()

        # Get slow query count in last hour
        one_hour_ago = datetime.now(IST) - timedelta(hours=1)
        recent_slow_queries = [
            q for q in self.query_log
            if datetime.fromisoformat(q["timestamp"]) > one_hour_ago
        ]

        # Calculate average query time for recent slow queries
        if recent_slow_queries:
            avg_slow_time = sum(q["duration"] for q in recent_slow_queries) / len(recent_slow_queries)
        else:
            avg_slow_time = 0

        return {
            "connection_pool": conn_stats,
            "slow_queries_last_hour": len(recent_slow_queries),
            "average_slow_query_time": avg_slow_time,
            "total_slow_queries_logged": len(self.query_log),
            "timestamp": datetime.now(IST).isoformat()
        }

    def log_performance_metrics(self):
        """Log current performance metrics"""
        metrics = self.get_performance_metrics()

        logger.info(f"DB Performance Metrics: "
                   f"Active Connections: {metrics['connection_pool']['active_connections']}, "
                   f"Slow Queries (1h): {metrics['slow_queries_last_hour']}, "
                   f"Avg Slow Query Time: {metrics['average_slow_query_time']:.2f}s")

        # Cache metrics for monitoring endpoints
        cache.set("db_performance_metrics", metrics, ttl_seconds=300)  # 5 minutes

# Global monitor instance
db_monitor = DatabaseMonitor()

# Monitoring endpoints helpers
def get_db_metrics() -> Dict:
    """Get cached database metrics"""
    cached = cache.get("db_performance_metrics")
    if cached:
        return cached

    # Fallback to real-time metrics
    return db_monitor.get_performance_metrics()

def get_connection_health() -> Dict:
    """Check database connection health"""
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db.close()

        return {
            "status": "healthy",
            "timestamp": datetime.now(IST).isoformat(),
            "message": "Database connection successful"
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(IST).isoformat(),
            "error": str(e)
        }

# Periodic monitoring task
async def monitor_database_periodically():
    """Background task to periodically log database metrics"""
    while True:
        try:
            db_monitor.log_performance_metrics()
            await asyncio.sleep(300)  # Every 5 minutes
        except Exception as e:
            logger.error(f"Database monitoring task failed: {e}")
            await asyncio.sleep(60)  # Retry in 1 minute