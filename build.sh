#!/bin/bash

# Stop and remove existing containers
docker compose down

# Remove existing images for this project
docker compose down --rmi all

# Remove dangling images
docker image prune -f

# Build fresh images
docker compose build --no-cache

echo "Fresh images built successfully!"
