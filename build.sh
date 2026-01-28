#!/bin/bash

# Fleet Manager Build Script with Automatic Cleanup
# This script builds fresh Docker images and cleans up old ones to save space

set -e

echo "=========================================="
echo "Fleet Manager - Build & Cleanup"
echo "=========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}[1/5]${NC} Stopping running containers..."
docker compose down --volumes || true
echo ""

echo -e "${GREEN}[2/5]${NC} Removing old project images..."
docker compose down --rmi all || true
echo ""

echo -e "${GREEN}[3/5]${NC} Cleaning up dangling images and volumes..."
docker image prune -f || true
docker volume prune -f || true
echo ""

echo -e "${GREEN}[4/5]${NC} Building fresh images (no cache)..."
docker compose build --no-cache
echo ""

echo -e "${GREEN}[5/5]${NC} Removing unused images created more than 72 hours ago..."
docker image prune -a -f --filter "until=72h" || true
echo ""

echo -e "${GREEN}✓ Fresh images built successfully!${NC}"
echo ""

# Show disk usage
echo "Current Docker disk usage:"
docker system df
echo ""

echo -e "${YELLOW}Next steps:${NC}"
echo "1. Review the images above"
echo "2. Run 'docker compose up -d' to start services"
echo "3. Run './cleanup_docker.sh' periodically to free up space"
