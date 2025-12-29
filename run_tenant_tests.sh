#!/bin/bash
# Quick script to run tenant endpoint tests

echo "🧪 Running Fleet Manager Tenant Endpoint Tests"
echo "================================================"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null
then
    echo "❌ pytest not found. Installing test dependencies..."
    pip install pytest pytest-cov pytest-asyncio
    echo "✅ Test dependencies installed"
    echo ""
fi

# Run tests with coverage
echo "🚀 Running tests..."
pytest tests/test_tenant_endpoints.py -v --cov=app.routes.tenant_router --cov-report=term-missing

echo ""
echo "================================================"
echo "✅ Test run complete!"
