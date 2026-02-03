#!/bin/bash

# Fleet Manager Docker Cleanup Script
# This script safely removes old Docker images and frees up disk space
# Run this after deploying new images to production

set -e

echo "=========================================="
echo "Fleet Manager Docker Cleanup Script"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print with colors
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get initial disk usage
print_info "Getting Docker system information..."
echo ""
docker system df
echo ""

# Step 1: Remove dangling images (not referenced by any container)
print_info "Removing dangling images (untagged images)..."
DANGLING_COUNT=$(docker images -f "dangling=true" --format "{{.ID}}" | wc -l)
if [ "$DANGLING_COUNT" -gt 0 ]; then
    docker image prune -f
    print_info "Removed $DANGLING_COUNT dangling images"
else
    print_info "No dangling images found"
fi
echo ""

# Step 2: Remove unused images (not referenced by any container)
print_warning "Removing unused images (not running in any container)..."
UNUSED_COUNT=$(docker images --filter "dangling=false" --format "{{.Repository}}:{{.Tag}}" | wc -l)
echo "Found potentially unused images. Listing images in use:"
docker ps -a --format "table {{.Image}}" | sort | uniq
echo ""

# Ask for confirmation before removing
read -p "Remove unused images? This will free significant space. (yes/no): " -r
if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    docker image prune -a -f --filter "until=72h"
    print_info "Removed unused images created more than 72 hours ago"
else
    print_warning "Skipped removing unused images"
fi
echo ""

# Step 3: Remove dangling volumes
print_info "Removing dangling volumes..."
DANGLING_VOLUMES=$(docker volume ls -f "dangling=true" --format "{{.Name}}" | wc -l)
if [ "$DANGLING_VOLUMES" -gt 0 ]; then
    docker volume prune -f
    print_info "Removed $DANGLING_VOLUMES dangling volumes"
else
    print_info "No dangling volumes found"
fi
echo ""

# Step 4: Show final disk usage
print_info "Docker system information after cleanup:"
echo ""
docker system df
echo ""

# Step 5: Show breakdown by image (largest images)
print_info "Largest Docker images:"
echo ""
docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | sort -k3 -h -r | head -20
echo ""

print_info "Cleanup completed successfully!"
print_info "To further reduce space, you can:"
echo "  - Remove specific images: docker rmi <image_id>"
echo "  - Remove all stopped containers: docker container prune -f"
echo "  - Clear builder cache: docker builder prune -f"
echo ""
