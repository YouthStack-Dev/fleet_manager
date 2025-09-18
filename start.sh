#!/bin/bash

# Stop and remove existing containers
docker compose down

# Start services with fresh containers
docker compose up -d