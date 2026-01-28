#!/bin/bash

# Fleet Manager - Production Deployment with Docker Cleanup
# This script handles production deployment with automatic image cleanup

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
COMPOSE_FILE="docker-compose_prod.yaml"
COMPOSE_MONITORING_FILE="docker-compose.monitoring.yml"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=========================================="
echo "Fleet Manager - Production Deployment"
echo "==========================================${NC}"
echo ""

# Function to print sections
print_section() {
    echo -e "${GREEN}[$1]${NC} $2"
}

# Confirm deployment
echo -e "${YELLOW}WARNING: This will deploy to production${NC}"
read -p "Continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Deployment cancelled"
    exit 1
fi
echo ""

# Step 1: Check and backup current state
print_section "1/7" "Backing up current state..."
BACKUP_FILE="production_backup_$(date +%s).tar.gz"
docker compose -f "$COMPOSE_FILE" exec -T postgres pg_dump -U fleetadmin fleet_db | gzip > "$BACKUP_FILE"
echo "Database backup: $BACKUP_FILE"
echo ""

# Step 2: Show current disk usage
print_section "2/7" "Current Docker disk usage:"
docker system df
echo ""

# Step 3: Stop monitoring containers if running
print_section "3/7" "Stopping monitoring containers (if any)..."
docker compose -f "$COMPOSE_MONITORING_FILE" down --volumes 2>/dev/null || echo "Monitoring not running"
echo ""

# Step 4: Pull latest images
print_section "4/7" "Pulling latest production images..."
docker pull dheerajkumarp/fleet_service_manager:latest || echo "Image already up to date"
docker pull redis:7.4-alpine
docker pull postgres:15
echo ""

# Step 5: Start production services
print_section "5/7" "Starting production services..."
docker compose -f "$COMPOSE_FILE" down || true
docker compose -f "$COMPOSE_FILE" up -d
echo ""

# Wait for services to be healthy
print_section "5.5/7" "Waiting for services to be healthy..."
sleep 10
docker compose -f "$COMPOSE_FILE" ps
echo ""

# Step 6: Clean up old images
print_section "6/7" "Cleaning up old Docker images..."
print_section "6.1/7" "Removing dangling images..."
docker image prune -f || true

print_section "6.2/7" "Removing images older than 7 days..."
docker image prune -a -f --filter "until=168h" || true

print_section "6.3/7" "Removing dangling volumes..."
docker volume prune -f || true

print_section "6.4/7" "Clearing build cache..."
docker builder prune -f || true
echo ""

# Step 7: Show final disk usage
print_section "7/7" "Docker disk usage after cleanup:"
docker system df
echo ""

echo -e "${GREEN}=========================================="
echo "Deployment completed successfully!"
echo "==========================================${NC}"
echo ""
echo "Largest images running:"
docker images --filter "dangling=false" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | grep -v REPOSITORY | sort -k3 -h -r | head -10
echo ""
echo "Running containers:"
docker ps --format "table {{.Image}}\t{{.Status}}"
echo ""

# Verify service is running
print_section "Verification" "Testing service health..."
sleep 5
if curl -s http://localhost:8100/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Service is healthy${NC}"
else
    echo -e "${YELLOW}⚠ Service health check pending (may take a moment)${NC}"
fi
echo ""
