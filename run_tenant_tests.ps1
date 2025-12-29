# Quick script to run tenant endpoint tests (PowerShell)

Write-Host "🧪 Running Fleet Manager Tenant Endpoint Tests" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if pytest is installed
$pytestInstalled = Get-Command pytest -ErrorAction SilentlyContinue
if (-not $pytestInstalled) {
    Write-Host "❌ pytest not found. Installing test dependencies..." -ForegroundColor Yellow
    pip install pytest pytest-cov pytest-asyncio
    Write-Host "✅ Test dependencies installed" -ForegroundColor Green
    Write-Host ""
}

# Run tests with coverage
Write-Host "🚀 Running tests..." -ForegroundColor Cyan
pytest tests/test_tenant_endpoints.py -v --cov=app.routes.tenant_router --cov-report=term-missing

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "✅ Test run complete!" -ForegroundColor Green
