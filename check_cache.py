#!/usr/bin/env python3
"""
Cache Monitoring Script for Fleet Manager
Shows cache status, keys, and performance metrics
"""
import os
import sys
sys.path.append('.')

from app.utils.cache_manager import get_cache_stats, cache
from app.config import settings

def check_cache_status():
    """Check if Redis cache is available and working"""
    print("🔍 Fleet Manager Cache Status Check")
    print("=" * 50)

    # Check Redis configuration
    print(f"Redis Host: {settings.REDIS_HOST}")
    print(f"Redis Port: {settings.REDIS_PORT}")
    print(f"Redis DB: {settings.REDIS_DB}")
    print(f"Redis Password: {'Set' if settings.REDIS_PASSWORD else 'Not Set'}")
    print(f"Use Redis: {'Enabled' if settings.USE_REDIS else 'Disabled'}")
    print()

    if not settings.USE_REDIS:
        print("⚠️  Redis is DISABLED in configuration")
        print("   To enable Redis, set environment variable: USE_REDIS=1")
        print("   Or update your .env file with: USE_REDIS=1")
        return

    # Get cache statistics
    try:
        stats = get_cache_stats()
        print("📊 Cache Statistics:")
        print(f"   Status: {'✅ Healthy' if stats.get('status') == 'healthy' else '❌ Unhealthy'}")

        if stats.get('status') == 'healthy':
            print(f"   Connected Clients: {stats.get('connected_clients', 'N/A')}")
            print(f"   Memory Used: {stats.get('used_memory', 'N/A')}")
            print(f"   Total Connections: {stats.get('total_connections_received', 'N/A')}")
            print(f"   Commands Processed: {stats.get('total_commands_processed', 'N/A')}")
            print(f"   Uptime: {stats.get('uptime_in_seconds', 0) // 3600} hours")
            print(f"   Hit Rate: {stats.get('hit_rate', 0):.1f}%")
        else:
            print(f"   Error: {stats.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"❌ Error getting cache stats: {e}")

    print()

    # Try to list cache keys
    try:
        keys = cache.redis_client.keys('*')
        print(f"🔑 Cache Keys ({len(keys)} total):")
        if keys:
            for i, key in enumerate(keys[:20]):  # Show first 20 keys
                try:
                    ttl = cache.redis_client.ttl(key)
                    print(f"   {i+1:2d}. {key.decode() if isinstance(key, bytes) else key} (TTL: {ttl}s)")
                except:
                    print(f"   {i+1:2d}. {key}")
            if len(keys) > 20:
                print(f"   ... and {len(keys) - 20} more keys")
        else:
            print("   No keys found in cache")
    except Exception as e:
        print(f"❌ Error listing cache keys: {e}")

    print()

def show_cached_endpoints():
    """Show which endpoints are cached and their TTL"""
    print("🎯 Cached Endpoints:")
    print("-" * 30)
    print("1. GET /api/v1/routes - Route listings (3 minutes)")
    print("   Cache key: routes:{tenant_id}:{shift_id}:{date}:{status}")
    print()
    print("2. GET /api/v1/routes/unrouted - Unrouted bookings (2 minutes)")
    print("   Cache key: unrouted:{tenant_id}:{shift_id}:{date}")
    print()
    print("3. GET /api/v1/reports/bookings/analytics - Booking analytics (5 minutes)")
    print("   Cache key: analytics:{tenant_id}:{start_date}:{end_date}")
    print()
    print("4. Background Tasks:")
    print("   - Route optimization results: route_result:{task_id}")
    print("   - Report generation results: report:{task_id}")
    print()
    print("5. Sessions & OTP:")
    print("   - User sessions: session:{session_id}")
    print("   - OTP codes: otp:{phone_number}")
    print()

def show_monitoring_endpoints():
    """Show monitoring API endpoints"""
    print("📡 Monitoring Endpoints:")
    print("-" * 25)
    print("GET /api/v1/monitoring/health - Overall system health")
    print("GET /api/v1/monitoring/cache/stats - Cache statistics")
    print("GET /api/v1/monitoring/database/metrics - Database metrics")
    print("GET /api/v1/monitoring/system/info - System information")
    print("GET /api/v1/monitoring/tasks/{task_id} - Background task status")
    print()

if __name__ == "__main__":
    check_cache_status()
    show_cached_endpoints()
    show_monitoring_endpoints()

    print("💡 Tips:")
    print("- Cache improves performance by reducing database queries")
    print("- Use monitoring endpoints to check cache hit rates")
    print("- Background tasks store results in cache for quick retrieval")
    print("- Sessions and OTP are cached for security and performance")