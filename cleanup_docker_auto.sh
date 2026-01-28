#!/bin/bash

# Fleet Manager - Automated Docker Image Cleanup Policy
# This script implements a retention policy to automatically clean old images
# Add this to crontab to run periodically: 0 2 * * * /path/to/cleanup_docker_auto.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_FILE="${SCRIPT_DIR}/logs/docker_cleanup.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "======================================"
log "Starting automated Docker cleanup"
log "======================================"

# Policy: Keep images from last 7 days, remove older unused images
log "Removing images created more than 7 days ago..."
REMOVED=$(docker image prune -a -f --filter "until=168h" 2>&1 | tail -1)
log "Prune result: $REMOVED"

# Remove dangling volumes (not attached to any container)
log "Removing dangling volumes..."
VOLUME_REMOVED=$(docker volume prune -f 2>&1 | tail -1)
log "Volume prune result: $VOLUME_REMOVED"

# Remove dangling build cache
log "Removing dangling build cache..."
CACHE_REMOVED=$(docker builder prune -f 2>&1 | tail -1)
log "Build cache prune result: $CACHE_REMOVED"

# Get current disk usage
log "Current Docker system usage:"
docker system df | while read line; do log "$line"; done

log "Automated cleanup completed successfully"
log "======================================"
echo ""
