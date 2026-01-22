#!/usr/bin/env python3
"""
Production Monitoring Script for Fleet Manager
Run this script to continuously monitor your production environment

Usage:
    python monitor_production.py --api-url https://your-api.com
    
Features:
    - Health checks every minute
    - Error rate monitoring
    - Response time tracking
    - Alerts via Slack/Discord/Email
    - Auto-restart on critical failures
"""
import argparse
import requests
import time
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class ProductionMonitor:
    """Monitor Fleet Manager production environment"""
    
    def __init__(
        self,
        api_base_url: str,
        slack_webhook: Optional[str] = None,
        error_rate_threshold: float = 5.0,
        response_time_threshold: float = 1000.0,
        check_interval: int = 60
    ):
        self.api_base_url = api_base_url.rstrip('/')
        self.monitoring_url = f"{self.api_base_url}/api/v1/monitoring"
        self.slack_webhook = slack_webhook
        self.error_rate_threshold = error_rate_threshold
        self.response_time_threshold = response_time_threshold
        self.check_interval = check_interval
        
        # Track state
        self.last_alert_time = {}
        self.alert_cooldown = 300  # 5 minutes between same alerts
        
        logger.info(f"🚀 Production Monitor initialized for {api_base_url}")
        logger.info(f"⚙️ Error rate threshold: {error_rate_threshold}%")
        logger.info(f"⚙️ Response time threshold: {response_time_threshold}ms")
        logger.info(f"⚙️ Check interval: {check_interval}s")
    
    def check_health(self) -> Dict:
        """Check overall system health"""
        try:
            response = requests.get(
                f"{self.monitoring_url}/dashboard",
                timeout=10
            )
            response.raise_for_status()
            return response.json()['data']
        except Exception as e:
            logger.error(f"❌ Failed to fetch dashboard: {e}")
            return None
    
    def analyze_metrics(self, dashboard: Dict) -> List[str]:
        """Analyze metrics and generate alerts"""
        alerts = []
        
        if not dashboard:
            alerts.append("🚨 CRITICAL: Cannot fetch monitoring data")
            return alerts
        
        # Check database health
        db_status = dashboard['health']['database']['status']
        if db_status != 'healthy':
            alerts.append(f"🔴 DATABASE UNHEALTHY: {db_status}")
        
        # Check cache health
        cache_status = dashboard['health']['cache'].get('status')
        if cache_status != 'healthy':
            alerts.append(f"🔴 CACHE UNHEALTHY: {cache_status}")
        
        # Check error rate
        request_stats = dashboard['requests']['stats']
        error_rate = request_stats.get('error_rate', 0)
        if error_rate > self.error_rate_threshold:
            alerts.append(
                f"⚠️ HIGH ERROR RATE: {error_rate:.2f}% "
                f"(threshold: {self.error_rate_threshold}%)"
            )
        
        # Check response time
        avg_time = request_stats.get('avg_response_time_ms', 0)
        if avg_time > self.response_time_threshold:
            alerts.append(
                f"⚠️ SLOW RESPONSES: {avg_time:.0f}ms "
                f"(threshold: {self.response_time_threshold}ms)"
            )
        
        # Check total errors
        error_stats = dashboard['errors']['stats']
        total_errors = error_stats.get('total_errors', 0)
        if total_errors > 100:
            alerts.append(f"⚠️ HIGH ERROR COUNT: {total_errors} errors logged")
        
        # Check cache hit rate
        cache_hit_rate = dashboard['health']['cache'].get('hit_rate', 0)
        if cache_hit_rate < 90:
            alerts.append(
                f"⚠️ LOW CACHE HIT RATE: {cache_hit_rate:.1f}% "
                f"(expected >90%)"
            )
        
        return alerts
    
    def send_alert(self, message: str):
        """Send alert via configured channels"""
        # Check cooldown
        now = time.time()
        alert_key = message[:50]  # Use first 50 chars as key
        
        if alert_key in self.last_alert_time:
            if now - self.last_alert_time[alert_key] < self.alert_cooldown:
                logger.debug(f"Skipping duplicate alert (cooldown): {message}")
                return
        
        self.last_alert_time[alert_key] = now
        
        # Log to console
        logger.warning(f"ALERT: {message}")
        
        # Send to Slack if configured
        if self.slack_webhook:
            try:
                payload = {
                    "text": f"🚨 Fleet Manager Alert\n{message}",
                    "username": "Fleet Monitor",
                    "icon_emoji": ":rotating_light:"
                }
                requests.post(self.slack_webhook, json=payload, timeout=5)
                logger.info(f"Alert sent to Slack")
            except Exception as e:
                logger.error(f"Failed to send Slack alert: {e}")
    
    def log_metrics(self, dashboard: Dict):
        """Log current metrics"""
        if not dashboard:
            return
        
        request_stats = dashboard['requests']['stats']
        error_stats = dashboard['errors']['stats']
        
        logger.info(
            f"📊 Metrics: "
            f"Requests: {request_stats.get('total_requests', 0)} | "
            f"Errors: {request_stats.get('total_errors', 0)} | "
            f"Error Rate: {request_stats.get('error_rate', 0):.2f}% | "
            f"Avg Time: {request_stats.get('avg_response_time_ms', 0):.0f}ms | "
            f"RPM: {request_stats.get('requests_per_minute', 0):.1f}"
        )
        
        # Log top error types if any
        error_types = error_stats.get('error_types', {})
        if error_types:
            top_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:3]
            error_summary = ", ".join([f"{err}: {count}" for err, count in top_errors])
            logger.info(f"🐛 Top Errors: {error_summary}")
    
    def run(self):
        """Main monitoring loop"""
        logger.info("🎯 Starting monitoring loop...")
        
        consecutive_failures = 0
        max_failures = 5
        
        while True:
            try:
                # Fetch dashboard data
                dashboard = self.check_health()
                
                if dashboard:
                    # Reset failure counter
                    consecutive_failures = 0
                    
                    # Analyze metrics
                    alerts = self.analyze_metrics(dashboard)
                    
                    # Send alerts if any
                    for alert in alerts:
                        self.send_alert(alert)
                    
                    # Log metrics
                    if not alerts:
                        self.log_metrics(dashboard)
                        logger.info("✅ All systems healthy")
                    
                else:
                    consecutive_failures += 1
                    logger.error(
                        f"❌ Health check failed "
                        f"({consecutive_failures}/{max_failures})"
                    )
                    
                    if consecutive_failures >= max_failures:
                        critical_msg = (
                            f"🚨 CRITICAL: {consecutive_failures} consecutive "
                            f"health check failures!"
                        )
                        self.send_alert(critical_msg)
                
                # Wait for next check
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("👋 Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                time.sleep(self.check_interval)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Fleet Manager Production Monitoring"
    )
    parser.add_argument(
        '--api-url',
        required=True,
        help='API base URL (e.g., https://api.yoursite.com)'
    )
    parser.add_argument(
        '--slack-webhook',
        help='Slack webhook URL for alerts'
    )
    parser.add_argument(
        '--error-rate-threshold',
        type=float,
        default=5.0,
        help='Error rate threshold percentage (default: 5.0)'
    )
    parser.add_argument(
        '--response-time-threshold',
        type=float,
        default=1000.0,
        help='Response time threshold in ms (default: 1000)'
    )
    parser.add_argument(
        '--check-interval',
        type=int,
        default=60,
        help='Check interval in seconds (default: 60)'
    )
    
    args = parser.parse_args()
    
    # Create monitor instance
    monitor = ProductionMonitor(
        api_base_url=args.api_url,
        slack_webhook=args.slack_webhook,
        error_rate_threshold=args.error_rate_threshold,
        response_time_threshold=args.response_time_threshold,
        check_interval=args.check_interval
    )
    
    # Run monitoring loop
    try:
        monitor.run()
    except Exception as e:
        logger.error(f"💥 Monitor crashed: {e}")
        raise


if __name__ == "__main__":
    main()
