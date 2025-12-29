# Fleet Manager Test Suite

## Overview
This directory contains comprehensive test suites for the Fleet Manager application, focusing on API endpoint testing, integration testing, and unit testing.

## Structure
```
tests/
├── __init__.py
├── conftest.py              # Pytest configuration and fixtures
├── test_tenant_endpoints.py # Tenant API endpoint tests
└── README.md                # This file
```

## Setup

### 1. Install Test Dependencies
```bash
pip install pytest pytest-cov pytest-asyncio httpx
```

Or add to `requirements.txt`:
```
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-asyncio>=0.21.0
httpx>=0.24.0
```

### 2. Environment Configuration
The tests use an in-memory SQLite database by default, so no additional database setup is required.

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest tests/test_tenant_endpoints.py
```

### Run Specific Test Class
```bash
pytest tests/test_tenant_endpoints.py::TestCreateTenant
```

### Run Specific Test Method
```bash
pytest tests/test_tenant_endpoints.py::TestCreateTenant::test_create_tenant_success_as_admin
```

### Run with Coverage Report
```bash
pytest --cov=app --cov-report=html
```

### Run with Verbose Output
```bash
pytest -v
```

### Run with Output Display
```bash
pytest -s
```

### Run Only Integration Tests
```bash
pytest -m integration
```

### Run Only Unit Tests
```bash
pytest -m unit
```

## Test Coverage

### Tenant Endpoints (`test_tenant_endpoints.py`)

#### 1. **Create Tenant** (`POST /tenants/`)
- ✅ Successful creation by admin
- ✅ Duplicate tenant_id rejection
- ✅ Duplicate tenant name rejection
- ✅ Invalid permission IDs handling
- ✅ Missing required fields validation
- ✅ Employee forbidden access
- ✅ Vendor forbidden access
- ✅ Unauthorized access rejection
- ✅ Minimal data creation

#### 2. **List Tenants** (`GET /tenants/`)
- ✅ Admin can list all tenants
- ✅ Employee can only see their tenant
- ✅ Name filter functionality
- ✅ Active status filter
- ✅ Pagination support
- ✅ Vendor forbidden access
- ✅ Unauthorized access rejection

#### 3. **Get Single Tenant** (`GET /tenants/{tenant_id}`)
- ✅ Admin can get any tenant
- ✅ Employee can get own tenant
- ✅ Employee gets own tenant when requesting others
- ✅ Not found error handling
- ✅ Vendor forbidden access
- ✅ Unauthorized access rejection

#### 4. **Update Tenant** (`PUT /tenants/{tenant_id}`)
- ✅ Admin can update tenant
- ✅ Permission updates
- ✅ Invalid permission handling
- ✅ Not found error handling
- ✅ Employee forbidden access
- ✅ Vendor forbidden access
- ✅ Partial updates support
- ✅ Unauthorized access rejection

#### 5. **Toggle Tenant Status** (`PATCH /tenants/{tenant_id}/toggle-status`)
- ✅ Admin can toggle status
- ✅ Double toggle returns to original
- ✅ Not found error handling
- ✅ Employee forbidden access
- ✅ Vendor forbidden access
- ✅ Unauthorized access rejection

#### 6. **Integration Tests**
- ✅ Complete CRUD lifecycle
- ✅ Tenant isolation verification

## Fixtures

### Database Fixtures
- **`test_db`**: Fresh in-memory SQLite database for each test
- **`client`**: FastAPI TestClient with database override

### Authentication Fixtures
- **`admin_user`**: System admin user with full permissions
- **`employee_user`**: Regular employee with limited permissions
- **`admin_token`**: JWT token for admin authentication
- **`employee_token`**: JWT token for employee authentication
- **`vendor_token`**: JWT token for vendor (limited access)

### Data Fixtures
- **`seed_permissions`**: Basic permissions for testing
- **`sample_tenant_data`**: Sample tenant creation payload

## Writing New Tests

### Test Structure
```python
class TestYourFeature:
    """Test suite for your feature."""
    
    def test_success_case(self, client, admin_token):
        """Test successful operation."""
        response = client.get("/endpoint", headers={"Authorization": admin_token})
        assert response.status_code == 200
        assert response.json()["success"] is True
    
    def test_error_case(self, client):
        """Test error handling."""
        response = client.get("/endpoint")
        assert response.status_code == 401
```

### Best Practices
1. **Use descriptive test names** - Test name should describe what is being tested
2. **One assertion per logical concept** - Keep tests focused
3. **Use fixtures** - Reuse common setup code
4. **Test edge cases** - Don't just test happy paths
5. **Test permissions** - Verify role-based access control
6. **Clean up** - Tests should be independent and not affect each other

## Continuous Integration

### GitHub Actions Example
```yaml
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: pytest --cov=app --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## Common Issues

### Issue: Import Errors
**Solution**: Make sure you're running pytest from the project root directory:
```bash
cd /path/to/fleet_manager
pytest
```

### Issue: Database Connection Errors
**Solution**: Tests use in-memory SQLite, so no external database is needed. If you see connection errors, check that SQLAlchemy models are properly imported in `conftest.py`.

### Issue: Token Expiration
**Solution**: The test tokens have a default expiration. If tests fail due to token expiration, the token fixtures generate fresh tokens for each test.

### Issue: Permission Errors
**Solution**: Ensure `seed_permissions` fixture is being used and permissions are properly created in the test database.

## Test Data Management

### Creating Test Data
Use fixtures to create consistent test data:
```python
@pytest.fixture
def sample_tenant(test_db):
    tenant = Tenant(tenant_id="TEST001", name="Test Tenant", ...)
    test_db.add(tenant)
    test_db.commit()
    return tenant
```

### Cleaning Up
The `test_db` fixture automatically cleans up after each test by dropping all tables.

## Debugging Tests

### Run with pdb
```bash
pytest --pdb
```

### Print statements
```bash
pytest -s
```

### Show local variables on failure
```bash
pytest -l
```

## Performance

### Parallel Execution
Install pytest-xdist:
```bash
pip install pytest-xdist
pytest -n auto
```

## Next Steps

1. Add tests for other endpoints (employees, bookings, etc.)
2. Add performance/load tests
3. Add security tests
4. Increase code coverage to 90%+
5. Set up CI/CD pipeline

## Contributing

When adding new features:
1. Write tests first (TDD approach recommended)
2. Ensure all tests pass before committing
3. Maintain test coverage above 80%
4. Update this README with new test information

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#session-external-transaction)
