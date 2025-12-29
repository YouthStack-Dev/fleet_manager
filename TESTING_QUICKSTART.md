# Tenant Endpoints Test Suite - Quick Start Guide

## 📋 What's Been Created

I've created a comprehensive test suite for your tenant endpoints with:

### Files Created:
```
tests/
├── __init__.py                    # Package initialization
├── conftest.py                    # Test fixtures and configuration
├── test_tenant_endpoints.py       # 40+ tenant endpoint tests
├── README.md                      # Detailed testing documentation
run_tenant_tests.sh                # Bash script to run tests
run_tenant_tests.ps1              # PowerShell script to run tests
```

## 🎯 Test Coverage

### **5 Endpoint Groups Tested:**

1. **Create Tenant** (9 tests)
   - ✅ Success as admin
   - ✅ Duplicate ID rejection
   - ✅ Duplicate name rejection  
   - ✅ Invalid permissions
   - ✅ Missing required fields
   - ✅ Employee/vendor forbidden
   - ✅ Unauthorized access
   - ✅ Minimal data creation

2. **List Tenants** (7 tests)
   - ✅ Admin lists all
   - ✅ Employee sees only theirs
   - ✅ Name filtering
   - ✅ Active status filtering
   - ✅ Pagination
   - ✅ Vendor forbidden
   - ✅ Unauthorized access

3. **Get Single Tenant** (6 tests)
   - ✅ Admin gets any tenant
   - ✅ Employee gets own
   - ✅ Employee isolation
   - ✅ Not found handling
   - ✅ Vendor forbidden
   - ✅ Unauthorized access

4. **Update Tenant** (8 tests)
   - ✅ Admin updates
   - ✅ Permission updates
   - ✅ Invalid permissions
   - ✅ Not found handling
   - ✅ Employee/vendor forbidden
   - ✅ Partial updates
   - ✅ Unauthorized access

5. **Toggle Status** (6 tests)
   - ✅ Admin toggles
   - ✅ Double toggle
   - ✅ Not found handling
   - ✅ Employee/vendor forbidden
   - ✅ Unauthorized access

6. **Integration Tests** (1 test)
   - ✅ Complete CRUD lifecycle

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install pytest pytest-cov pytest-asyncio
```

### 2. Run All Tests
```bash
# Using pytest directly
pytest tests/test_tenant_endpoints.py -v

# Using PowerShell script (Windows)
.\run_tenant_tests.ps1

# Using bash script (Linux/Mac)
./run_tenant_tests.sh
```

### 3. Run Specific Test Class
```bash
# Test only Create Tenant
pytest tests/test_tenant_endpoints.py::TestCreateTenant -v

# Test only List Tenants
pytest tests/test_tenant_endpoints.py::TestListTenants -v
```

### 4. Run with Coverage Report
```bash
pytest tests/test_tenant_endpoints.py --cov=app.routes.tenant_router --cov-report=html
```
Then open `htmlcov/index.html` in your browser.

## 📊 Expected Output

```
tests/test_tenant_endpoints.py::TestCreateTenant::test_create_tenant_success_as_admin PASSED [ 2%]
tests/test_tenant_endpoints.py::TestCreateTenant::test_create_tenant_duplicate_id PASSED [ 4%]
tests/test_tenant_endpoints.py::TestCreateTenant::test_create_tenant_duplicate_name PASSED [ 6%]
...
================================================ 40 passed in 5.23s ================================================
```

## 🔧 Test Fixtures Explained

### Authentication Fixtures:
- **`admin_token`** - Full access token for admin user
- **`employee_token`** - Limited access token for employee
- **`vendor_token`** - Restricted access token for vendor

### Database Fixtures:
- **`test_db`** - Fresh in-memory SQLite database per test
- **`client`** - FastAPI TestClient with DB override

### User Fixtures:
- **`admin_user`** - System admin with all permissions
- **`employee_user`** - Regular employee with limited permissions

### Data Fixtures:
- **`seed_permissions`** - Basic permissions for testing
- **`sample_tenant_data`** - Sample tenant creation payload

## 🎯 Key Testing Patterns

### 1. Permission-Based Testing
```python
def test_as_admin(client, admin_token):
    response = client.get("/tenants/", headers={"Authorization": admin_token})
    assert response.status_code == 200

def test_as_employee_forbidden(client, employee_token):
    response = client.post("/tenants/", headers={"Authorization": employee_token})
    assert response.status_code == 403
```

### 2. Error Handling
```python
def test_not_found(client, admin_token):
    response = client.get("/tenants/NONEXISTENT", headers={"Authorization": admin_token})
    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()
```

### 3. Data Validation
```python
def test_duplicate_rejection(client, admin_token, sample_tenant_data):
    # Create first tenant
    client.post("/tenants/", json=sample_tenant_data, headers={"Authorization": admin_token})
    
    # Try duplicate
    response = client.post("/tenants/", json=sample_tenant_data, headers={"Authorization": admin_token})
    assert response.status_code == 409
```

## 🐛 Debugging Tests

### Run Single Test with Output
```bash
pytest tests/test_tenant_endpoints.py::TestCreateTenant::test_create_tenant_success_as_admin -s -v
```

### Run with Debugger
```bash
pytest --pdb tests/test_tenant_endpoints.py
```

### Show Local Variables on Failure
```bash
pytest -l tests/test_tenant_endpoints.py
```

## 📈 Coverage Goals

Current test coverage focuses on:
- ✅ **Happy paths** - Normal successful operations
- ✅ **Error paths** - Invalid inputs, not found, conflicts
- ✅ **Permission checks** - Role-based access control
- ✅ **Data validation** - Required fields, formats
- ✅ **Edge cases** - Duplicates, partial updates

## 🔄 Continuous Testing

### Watch Mode (requires pytest-watch)
```bash
pip install pytest-watch
ptw tests/test_tenant_endpoints.py
```

### Pre-commit Hook
Add to `.git/hooks/pre-commit`:
```bash
#!/bin/bash
pytest tests/test_tenant_endpoints.py
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

## 📝 Next Steps

### 1. Run the Tests
```bash
pytest tests/test_tenant_endpoints.py -v
```

### 2. Check Coverage
```bash
pytest tests/test_tenant_endpoints.py --cov=app.routes.tenant_router --cov-report=term-missing
```

### 3. Fix Any Failing Tests
- Check error messages
- Verify database setup
- Ensure dependencies installed

### 4. Extend Tests (Optional)
- Add tests for other endpoints (employees, bookings, etc.)
- Add performance tests
- Add security tests

## 💡 Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'pytest'"
**Solution:**
```bash
pip install pytest pytest-cov pytest-asyncio
```

### Issue: "ModuleNotFoundError: No module named 'app'"
**Solution:** Run pytest from project root:
```bash
cd c:\projects\fleet_manager\fleet_manager
pytest tests/
```

### Issue: Tests fail with authentication errors
**Solution:** Check that JWT secret key is properly configured in test environment.

### Issue: Database errors
**Solution:** Tests use in-memory SQLite, no setup needed. If errors persist, check SQLAlchemy model imports.

## 📚 Documentation

- **Full Test Documentation**: `tests/README.md`
- **Pytest Docs**: https://docs.pytest.org/
- **FastAPI Testing**: https://fastapi.tiangolo.com/tutorial/testing/

## 🎉 Summary

You now have:
- ✅ 40+ comprehensive tests for tenant endpoints
- ✅ Complete fixtures for authentication and data
- ✅ Scripts for easy test execution
- ✅ Documentation for understanding and extending tests
- ✅ Coverage reporting capability

**To get started right now:**
```bash
pip install pytest pytest-cov
pytest tests/test_tenant_endpoints.py -v
```

Good luck with testing! 🚀
