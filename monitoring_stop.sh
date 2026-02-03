#!/bin/bash

# Stop monitoring in production

set -e

echo "🛑 Stopping monitoring stack..."
echo ""

# Stop only monitoring containers, keep production running
docker compose -f docker-compose.monitoring.yml down

echo ""
echo "✅ Monitoring stopped!"
echo ""
echo "Production services still running:"
docker ps --format "table {{.Names}}\t{{.Status}}"
echo ""
echo "To start monitoring again: ./monitoring_start.sh"
echo ""
