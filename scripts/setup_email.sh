#!/bin/bash
# Quick Email Configuration Setup Script
# Run this on your production server

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Fleet Manager - Email Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if service.prod.env exists
if [ ! -f "service.prod.env" ]; then
    echo -e "${YELLOW}⚠️  service.prod.env not found!${NC}"
    echo ""
    echo "Creating from example file..."
    
    if [ -f "service.prod.env.example" ]; then
        cp service.prod.env.example service.prod.env
        echo -e "${GREEN}✅ Created service.prod.env${NC}"
        echo ""
        echo -e "${YELLOW}📝 IMPORTANT: Edit service.prod.env with your actual values${NC}"
        echo "   nano service.prod.env"
        echo ""
        exit 0
    else
        echo -e "${RED}❌ service.prod.env.example not found!${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✅ Found service.prod.env${NC}"
echo ""

# Check if SMTP settings are configured
echo "Checking SMTP configuration..."
if grep -q "your-email@gmail.com" service.prod.env; then
    echo -e "${YELLOW}⚠️  Default values detected in service.prod.env${NC}"
    echo "   Please update with your actual email credentials"
    echo ""
    echo "   Required values:"
    echo "   - SMTP_USERNAME"
    echo "   - SMTP_PASSWORD"
    echo "   - SENDER_EMAIL"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ SMTP configuration looks good${NC}"
echo ""

# Restart services
echo "Restarting services..."
docker-compose -f docker-compose_prod.yaml down
echo ""
docker-compose -f docker-compose_prod.yaml up -d

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Services restarted successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Wait for container to start
echo "Waiting for service to initialize..."
sleep 5

# Check if email service is configured
echo ""
echo "Checking email service status..."
docker logs service_manager 2>&1 | grep -i "email service" | tail -n 3

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Next Steps:${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "1. Test alert notification to verify email"
echo "2. Check logs: docker logs -f service_manager"
echo "3. Monitor alerts in the system"
echo ""
