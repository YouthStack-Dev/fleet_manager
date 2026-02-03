#!/bin/bash

# Start monitoring in production (FREE)

set -e

echo "🚀 Starting FREE monitoring stack in production..."
echo ""
echo "This will start:"
echo "  📊 Prometheus (metrics) - Port 9090"
echo "  📈 Grafana (dashboards) - Port 3000"
echo "  📋 Loki (logs) - Port 3100"
echo "  📝 Promtail (log collector)"
echo "  💻 Node Exporter (system metrics) - Port 9100"
echo ""

# Start monitoring alongside production services
docker compose -f docker-compose_prod.yaml -f docker-compose.monitoring.yml up -d

echo ""
echo "✅ Monitoring started successfully!"
echo ""
echo "Access monitoring:"
echo "  📊 Prometheus: http://localhost:9090 (or http://YOUR_SERVER_IP:9090)"
echo "  📈 Grafana: http://localhost:3000 (or http://YOUR_SERVER_IP:3000)"
echo "      Username: admin"
echo "      Password: admin123"
echo "      ⚠️  Change password after first login!"
echo ""
echo "  📋 Loki: http://localhost:3100"
echo ""
echo "Running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
