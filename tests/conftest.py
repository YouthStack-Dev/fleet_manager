"""
Pytest configuration and fixtures for testing.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import Mock, patch

from app.database.session import Base, get_db
from main import app
from app.models.iam.permission import Permission
from app.models.iam.policy import Policy
from app.models.iam.role import Role
from app.models.tenant import Tenant
from app.models.team import Team
from app.models.employee import Employee
from app.models.cutoff import Cutoff
from common_utils.auth.utils import hash_password, create_access_token


# Test database URL - using in-memory SQLite for tests
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def test_db():
    """
    Create a fresh test database for each test function.
    """
    # Create engine with in-memory SQLite
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create session factory
    TestingSessionLocal = sessionmaker(autoflush=False, bind=engine)
    
    # Create a session
    db = TestingSessionLocal()
    
    try:
        yield db
    finally:
        db.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db, monkeypatch):
    """
    Create a test client with database override and bypassed permission checking for tests.
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Mock PermissionChecker to decode JWT directly without caching or introspection
    from common_utils.auth.permission_checker import PermissionChecker
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from fastapi import Depends, Request
    import jwt
    from app.config import settings
    
    security = HTTPBearer()
    
    original_call = PermissionChecker.__call__
    
    async def mock_permission_checker_call(self, request: Request, user_data=None):
        """Mock __call__ that decodes JWT directly"""
        # Get the authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            from fastapi import HTTPException, status as http_status
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        
        token = auth_header.replace("Bearer ", "")
        
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            
            # Convert string permissions to the expected format
            permissions_strings = payload.get("permissions", [])
            permissions_formatted = []
            for perm_str in permissions_strings:
                parts = perm_str.rsplit(".", 1)
                if len(parts) == 2:
                    permissions_formatted.append({
                        "module": parts[0],
                        "action": [parts[1]]
                    })
            
            user_data = {
                "user_id": payload.get("user_id"),
                "user_type": payload.get("user_type"),
                "tenant_id": payload.get("tenant_id"),
                "vendor_id": payload.get("vendor_id"),
                "permissions": permissions_formatted,
                "email": payload.get("email"),
            }
            
            # Check if user has required permissions
            user_permissions = []
            for p in user_data.get("permissions", []):
                module = p.get("module", "")
                actions = p.get("action", [])
                user_permissions.extend([f"{module}.{action}" for action in actions])
            
            if not any(p in user_permissions for p in self.required_permissions):
                from fastapi import HTTPException, status as http_status
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )
            
            return user_data
        except jwt.InvalidTokenError:
            from fastapi import HTTPException, status as http_status
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    # Patch the PermissionChecker's __call__ method
    monkeypatch.setattr(PermissionChecker, "__call__", mock_permission_checker_call)
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def seed_permissions(test_db):
    """
    Seed basic permissions required for testing.
    """
    permissions = [
        Permission(
            permission_id=1,
            module="admin_tenant",
            action="create",
            description="Create tenant"
        ),
        Permission(
            permission_id=2,
            module="admin_tenant",
            action="read",
            description="Read tenant"
        ),
        Permission(
            permission_id=3,
            module="admin_tenant",
            action="update",
            description="Update tenant"
        ),
        Permission(
            permission_id=4,
            module="admin_tenant",
            action="delete",
            description="Delete tenant"
        ),
        Permission(
            permission_id=5,
            module="employee",
            action="read",
            description="Read employee"
        ),
        Permission(
            permission_id=6,
            module="team",
            action="create",
            description="Create team"
        ),
        Permission(
            permission_id=7,
            module="team",
            action="read",
            description="Read team"
        ),
        Permission(
            permission_id=8,
            module="team",
            action="update",
            description="Update team"
        ),
        Permission(
            permission_id=9,
            module="team",
            action="delete",
            description="Delete team"
        ),
        Permission(
            permission_id=10,
            module="employee",
            action="create",
            description="Create employee"
        ),
        Permission(
            permission_id=11,
            module="employee",
            action="update",
            description="Update employee"
        ),
        Permission(
            permission_id=12,
            module="employee",
            action="delete",
            description="Delete employee"
        ),
        Permission(
            permission_id=13,
            module="shift",
            action="create",
            description="Create shift"
        ),
        Permission(
            permission_id=14,
            module="shift",
            action="read",
            description="Read shift"
        ),
        Permission(
            permission_id=15,
            module="shift",
            action="update",
            description="Update shift"
        ),
        Permission(
            permission_id=16,
            module="shift",
            action="delete",
            description="Delete shift"
        ),
        Permission(
            permission_id=17,
            module="cutoff",
            action="read",
            description="Read cutoff"
        ),
        Permission(
            permission_id=18,
            module="cutoff",
            action="update",
            description="Update cutoff"
        ),
        Permission(
            permission_id=19,
            module="weekoff-config",
            action="read",
            description="Read weekoff config"
        ),
        Permission(
            permission_id=20,
            module="weekoff-config",
            action="update",
            description="Update weekoff config"
        ),
        Permission(
            permission_id=21,
            module="booking",
            action="create",
            description="Create booking"
        ),
        Permission(
            permission_id=22,
            module="booking",
            action="read",
            description="Read booking"
        ),
        Permission(
            permission_id=23,
            module="booking",
            action="update",
            description="Update booking"
        ),
        Permission(
            permission_id=24,
            module="booking",
            action="delete",
            description="Delete booking"
        ),
        # Route management permissions
        Permission(
            permission_id=25,
            module="route",
            action="create",
            description="Create route"
        ),
        Permission(
            permission_id=26,
            module="route",
            action="read",
            description="Read route"
        ),
        Permission(
            permission_id=27,
            module="route",
            action="update",
            description="Update route"
        ),
        Permission(
            permission_id=28,
            module="route",
            action="delete",
            description="Delete route"
        ),
        Permission(
            permission_id=29,
            module="route_vendor_assignment",
            action="create",
            description="Assign vendor to route"
        ),
        Permission(
            permission_id=30,
            module="route_vendor_assignment",
            action="read",
            description="Read vendor assignment"
        ),
        Permission(
            permission_id=31,
            module="route_vendor_assignment",
            action="update",
            description="Update vendor assignment"
        ),
        Permission(
            permission_id=32,
            module="route_vendor_assignment",
            action="delete",
            description="Delete vendor assignment"
        ),
        Permission(
            permission_id=33,
            module="route_vehicle_assignment",
            action="create",
            description="Assign vehicle to route"
        ),
        Permission(
            permission_id=34,
            module="route_vehicle_assignment",
            action="read",
            description="Read vehicle assignment"
        ),
        Permission(
            permission_id=35,
            module="route_vehicle_assignment",
            action="update",
            description="Update vehicle assignment"
        ),
        Permission(
            permission_id=36,
            module="route_vehicle_assignment",
            action="delete",
            description="Delete vehicle assignment"
        ),
        Permission(
            permission_id=37,
            module="route_merge",
            action="create",
            description="Merge routes"
        ),
        Permission(
            permission_id=38,
            module="route_merge",
            action="read",
            description="Read merge routes"
        ),
        Permission(
            permission_id=39,
            module="route_merge",
            action="update",
            description="Update merge routes"
        ),
        Permission(
            permission_id=40,
            module="route_merge",
            action="delete",
            description="Delete merge routes"
        ),
    ]
    
    for perm in permissions:
        test_db.add(perm)
    
    test_db.commit()
    return permissions


@pytest.fixture(scope="function")
def admin_user(test_db, seed_permissions):
    """
    Create an admin user with full permissions.
    """
    # Create a system tenant for admin
    tenant = Tenant(
        tenant_id="SYSTEM",
        name="System Tenant",
        address="System Address",
        latitude=0.0,
        longitude=0.0,
        is_active=True
    )
    test_db.add(tenant)
    
    # Create admin role (system role should have tenant_id=None)
    admin_role = Role(
        role_id=1,
        tenant_id=None,  # System roles must have NULL tenant_id
        name="SystemAdmin",
        description="System Administrator",
        is_system_role=True,
        is_active=True
    )
    test_db.add(admin_role)
    
    # Create Employee system role (required by employee CRUD) if it doesn't exist
    employee_system_role = test_db.query(Role).filter(Role.name == "Employee", Role.is_system_role == True).first()
    if not employee_system_role:
        employee_system_role = Role(
            role_id=3,
            tenant_id=None,
            name="Employee",
            description="System Employee Role",
            is_system_role=True,
            is_active=True
        )
        test_db.add(employee_system_role)
    
    # Create admin policy with all permissions
    policy = Policy(
        policy_id=1,
        tenant_id="SYSTEM",  # Admin policy is for SYSTEM tenant
        name="SystemAdminPolicy",
        description="System Admin Policy",
        is_active=True
    )
    test_db.add(policy)
    test_db.flush()
    
    # Attach permissions to policy
    policy.permissions = seed_permissions
    
    # Link role to policy
    admin_role.policies.append(policy)
    
    # Create team
    team = Team(
        team_id=1,
        tenant_id="SYSTEM",
        name="System Team",
        description="System Team",
        is_active=True
    )
    test_db.add(team)
    test_db.flush()
    
    # Create admin employee (employee is in SYSTEM tenant, uses system role)
    admin = Employee(
        employee_id=1,
        tenant_id="SYSTEM",
        role_id=admin_role.role_id,
        team_id=team.team_id,
        name="Admin User",
        employee_code="ADMIN001",
        email="admin@system.com",
        phone="+1234567890",
        password=hash_password("Admin@123"),
        is_active=True
    )
    test_db.add(admin)
    test_db.commit()
    
    return {
        "employee": admin,
        "tenant": tenant,
        "role": admin_role,
        "policy": policy
    }


@pytest.fixture(scope="function")
def employee_user(test_db, seed_permissions):
    """
    Create a regular employee user with limited permissions.
    """
    # Ensure Employee system role exists (needed by employee CRUD)
    employee_system_role = test_db.query(Role).filter(Role.name == "Employee", Role.is_system_role == True).first()
    if not employee_system_role:
        employee_system_role = Role(
            role_id=3,
            tenant_id=None,
            name="Employee",
            description="System Employee Role",
            is_system_role=True,
            is_active=True
        )
        test_db.add(employee_system_role)
        test_db.flush()
    
    # Create tenant
    tenant = Tenant(
        tenant_id="TEST001",
        name="Test Company",
        address="Test Address",
        latitude=10.0,
        longitude=20.0,
        is_active=True
    )
    test_db.add(tenant)
    
    # Create employee role
    role = Role(
        role_id=2,
        tenant_id="TEST001",
        name="Employee",
        description="Regular Employee",
        is_system_role=False,
        is_active=True
    )
    test_db.add(role)
    
    # Create employee policy with limited permissions
    policy = Policy(
        policy_id=2,
        tenant_id="TEST001",
        name="EmployeePolicy",
        description="Employee Policy",
        is_active=True
    )
    test_db.add(policy)
    
    # Create admin policy for tenant (required for tenant updates)
    admin_policy = Policy(
        policy_id=3,
        tenant_id="TEST001",
        name="TEST001_AdminPolicy",
        description="Admin Policy for TEST001",
        is_active=True
    )
    test_db.add(admin_policy)
    test_db.flush()
    
    # Attach only read permission to employee policy
    policy.permissions = [seed_permissions[1], seed_permissions[4], seed_permissions[6], seed_permissions[7], seed_permissions[8], seed_permissions[9], seed_permissions[10]]  # tenant.read, employee.read, team.create, team.read, team.update, employee.create, employee.update
    
    # Attach all permissions to admin policy
    admin_policy.permissions = seed_permissions
    
    # Link role to policy
    role.policies.append(policy)
    
    # Create team
    team = Team(
        team_id=2,
        tenant_id="TEST001",
        name="Test Team",
        description="Test Team",
        is_active=True
    )
    test_db.add(team)
    test_db.flush()
    
    # Create employee
    employee = Employee(
        employee_id=2,
        tenant_id="TEST001",
        role_id=role.role_id,
        team_id=team.team_id,
        name="Test Employee",
        employee_code="EMP001",
        email="employee@test.com",
        phone="+1234567891",
        password=hash_password("Employee@123"),
        is_active=True
    )
    test_db.add(employee)
    test_db.commit()
    
    return {
        "employee": employee,
        "tenant": tenant,
        "role": role,
        "policy": policy
    }


@pytest.fixture(scope="function")
def test_role(test_db):
    """
    Create a test Driver role for driver tests.
    """
    # Check if Driver role already exists
    driver_role = test_db.query(Role).filter(Role.name == "Driver", Role.is_system_role == True).first()
    if not driver_role:
        driver_role = Role(
            tenant_id=None,
            name="Driver",
            description="System Driver Role",
            is_system_role=True,
            is_active=True
        )
        test_db.add(driver_role)
        test_db.commit()
        test_db.refresh(driver_role)
    
    return driver_role


@pytest.fixture(scope="function")
def admin_token(admin_user):
    """
    Generate JWT token for admin user.
    """
    token = create_access_token(
        user_id=str(admin_user["employee"].employee_id),
        tenant_id="TEST001",  # Use TEST001 for test consistency
        user_type="admin",
        custom_claims={
            "email": admin_user["employee"].email,
            "permissions": [
                "admin_tenant.create", "admin_tenant.read", "admin_tenant.update", "admin_tenant.delete",
                "team.create", "team.read", "team.update", "team.delete",
                "employee.create", "employee.read", "employee.update", "employee.delete",
                "shift.create", "shift.read", "shift.update", "shift.delete",
                "cutoff.read", "cutoff.update",
                "weekoff-config.read", "weekoff-config.update",
                "booking.create", "booking.read", "booking.update", "booking.delete",
                "route.create", "route.read", "route.update", "route.delete",
                "route_vendor_assignment.create", "route_vendor_assignment.read", "route_vendor_assignment.update", "route_vendor_assignment.delete",
                "route_vehicle_assignment.create", "route_vehicle_assignment.read", "route_vehicle_assignment.update", "route_vehicle_assignment.delete",
                "route_merge.create", "route_merge.read", "route_merge.update", "route_merge.delete",
                "vehicle-type.create", "vehicle-type.read", "vehicle-type.update", "vehicle-type.delete",
                "vehicle.create", "vehicle.read", "vehicle.update", "vehicle.delete",
                "driver.create", "driver.read", "driver.update", "driver.delete",
                "vendor.create", "vendor.read", "vendor.update", "vendor.delete"
            ]
        }
    )
    return f"Bearer {token}"


@pytest.fixture(scope="function")
def employee_token(employee_user):
    """
    Generate JWT token for employee user.
    """
    token = create_access_token(
        user_id=str(employee_user["employee"].employee_id),
        tenant_id=employee_user["tenant"].tenant_id,
        user_type="employee",
        custom_claims={
            "email": employee_user["employee"].email,
            "permissions": [
                "admin_tenant.read", "employee.read", "employee.create", "employee.update",
                "team.create", "team.read", "team.update",
                "shift.create", "shift.read", "shift.update",
                "cutoff.read", "cutoff.update",
                "weekoff-config.read", "weekoff-config.update",
                "booking.create", "booking.read", "booking.update",
                "route.create", "route.read", "route.update", "route.delete",
                "route_vendor_assignment.create", "route_vendor_assignment.read", "route_vendor_assignment.update", "route_vendor_assignment.delete",
                "route_vehicle_assignment.create", "route_vehicle_assignment.read", "route_vehicle_assignment.update", "route_vehicle_assignment.delete",
                "route_merge.create", "route_merge.read", "route_merge.update", "route_merge.delete"
            ]
        }
    )
    return f"Bearer {token}"


@pytest.fixture(scope="function")
def vendor_token():
    """
    Generate JWT token for vendor user (limited access).
    """
    token = create_access_token(
        user_id="999",
        tenant_id="VENDOR001",
        user_type="vendor",
        custom_claims={
            "email": "vendor@test.com",
            "permissions": ["route.read"]
        }
    )
    return f"Bearer {token}"


@pytest.fixture(scope="function")
def sample_tenant_data():
    """
    Sample tenant creation data.
    """
    return {
        "tenant_id": "TENANT001",
        "name": "Test Tenant Company",
        "address": "123 Test Street, Test City",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "is_active": True,
        "permission_ids": [1, 2, 3, 4, 5],
        "employee_name": "John Doe",
        "employee_email": "john.doe@tenant001.com",
        "employee_phone": "+1234567890",
        "employee_password": "SecurePass@123",
        "employee_code": "EMP001",
        "employee_address": "456 Employee Street",
        "employee_latitude": 40.7128,
        "employee_longitude": -74.0060,
        "employee_gender": "Male"
    }


@pytest.fixture(scope="function")
def test_tenant(employee_user):
    """Return tenant from employee_user (TEST001) for consistent testing"""
    return employee_user["tenant"]


@pytest.fixture(scope="function")
def second_tenant(test_db):
    """Create a second tenant for testing cross-tenant isolation"""
    tenant = Tenant(
        tenant_id="TEST002",
        name="Second Test Company",
        address="Second Test Address",
        latitude=11.0,
        longitude=21.0,
        is_active=True
    )
    test_db.add(tenant)
    test_db.commit()
    test_db.refresh(tenant)
    return tenant


@pytest.fixture(scope="function")
def test_team(test_db, employee_user):
    """Create a test team for employee tests in TEST001 tenant"""
    team = Team(
        team_id=10,  # Use ID 10 to avoid conflicts
        tenant_id=employee_user["tenant"].tenant_id,
        name="Test Team for Employees",
        description="Team for employee tests",
        is_active=True
    )
    test_db.add(team)
    test_db.commit()
    test_db.refresh(team)
    return team


@pytest.fixture(scope="function")
def second_team(test_db, second_tenant):
    """Create a team in the second tenant"""
    team = Team(
        team_id=11,  # Use ID 11
        tenant_id=second_tenant.tenant_id,
        name="Second Tenant Team",
        description="Team for second tenant",
        is_active=True
    )
    test_db.add(team)
    test_db.commit()
    test_db.refresh(team)
    return team


@pytest.fixture(scope="function")
def second_team_same_tenant(test_db, employee_user):
    """Create a second team in the same tenant for testing team updates"""
    team = Team(
        team_id=12,  # Use ID 12
        tenant_id=employee_user["tenant"].tenant_id,
        name="Second Team Same Tenant",
        description="Another team in same tenant",
        is_active=True
    )
    test_db.add(team)
    test_db.commit()
    test_db.refresh(team)
    return team


@pytest.fixture(scope="function")
def test_employee(test_db, test_tenant, test_team):
    """Create a test employee"""
    # Get the system Employee role
    employee_role = test_db.query(Role).filter(Role.name == "Employee", Role.is_system_role == True).first()
    
    employee = Employee(
        employee_id=100,
        tenant_id=test_tenant.tenant_id,
        team_id=test_team.team_id,
        role_id=employee_role.role_id if employee_role else 3,
        name="Test Employee One",
        employee_code="TESTEMPLOYEE001",
        email="testemployee1@example.com",
        phone="+1234567800",
        password=hash_password("TestPass123!"),
        address="100 Test Street",
        latitude=40.7128,
        longitude=-74.0060,
        gender="Male",
        is_active=True
    )
    test_db.add(employee)
    test_db.commit()
    test_db.refresh(employee)
    return {
        "employee": employee,
        "tenant_id": employee.tenant_id,
        "team_id": employee.team_id
    }


@pytest.fixture(scope="function")
def test_shift(test_db, test_tenant):
    """Create a test shift in TEST001 tenant"""
    from app.models.shift import Shift
    from datetime import time
    shift = Shift(
        shift_id=20,
        tenant_id=test_tenant.tenant_id,
        shift_code="TEST_SHIFT_001",
        log_type="IN",
        shift_time=time(9, 0),
        pickup_type="Pickup",
        gender="Male",
        waiting_time_minutes=15,
        is_active=True
    )
    test_db.add(shift)
    test_db.commit()
    test_db.refresh(shift)
    return shift


@pytest.fixture(scope="function")
def second_shift(test_db, second_tenant):
    """Create a shift in second tenant for isolation testing"""
    from app.models.shift import Shift
    from datetime import time
    shift = Shift(
        shift_id=21,
        tenant_id=second_tenant.tenant_id,
        shift_code="TEST_SHIFT_002",
        log_type="OUT",
        shift_time=time(18, 0),
        pickup_type="Nodal",
        gender="Female",
        waiting_time_minutes=20,
        is_active=True
    )
    test_db.add(shift)
    test_db.commit()
    test_db.refresh(shift)
    return shift


@pytest.fixture(scope="function")
def second_employee(test_db, second_tenant, second_team):
    """Create an employee in the second tenant for isolation testing"""
    # Get the system Employee role
    employee_role = test_db.query(Role).filter(Role.name == "Employee", Role.is_system_role == True).first()
    
    employee = Employee(
        employee_id=101,
        tenant_id=second_tenant.tenant_id,
        team_id=second_team.team_id,
        role_id=employee_role.role_id if employee_role else 3,
        name="Second Tenant Employee",
        employee_code="TESTEMPLOYEE002",
        email="testemployee2@example.com",
        phone="+1234567801",
        password=hash_password("TestPass123!"),
        is_active=True
    )
    test_db.add(employee)
    test_db.commit()
    test_db.refresh(employee)
    return {
        "employee": employee,
        "tenant_id": employee.tenant_id,
        "team_id": employee.team_id
    }


# ==================== Route Management Fixtures ====================

@pytest.fixture(scope="function")
def test_vendor(test_db, test_tenant):
    """Create a test vendor"""
    from app.models.vendor import Vendor
    vendor = Vendor(
        vendor_id=1,
        tenant_id=test_tenant.tenant_id,
        vendor_code="VEND001",
        name="Test Vendor",
        email="vendor@test.com",
        phone="1234567890",
        is_active=True
    )
    test_db.add(vendor)
    test_db.commit()
    test_db.refresh(vendor)
    return vendor

@pytest.fixture(scope="function")
def second_vendor(test_db, second_tenant):
    """Create vendor in second tenant"""
    from app.models.vendor import Vendor
    vendor = Vendor(
        vendor_id=2,
        tenant_id=second_tenant.tenant_id,
        vendor_code="VEND002",
        name="Second Vendor",
        email="vendor2@test.com",
        phone="9876543210",
        is_active=True
    )
    test_db.add(vendor)
    test_db.commit()
    test_db.refresh(vendor)
    return vendor

@pytest.fixture(scope="function")
def test_driver(test_db, test_tenant, test_vendor):
    """Create a test driver"""
    from app.models.driver import Driver, GenderEnum, VerificationStatusEnum
    from datetime import date
    driver = Driver(
        driver_id=1,
        tenant_id=test_tenant.tenant_id,
        vendor_id=test_vendor.vendor_id,
        role_id=2,
        name="Test Driver",
        code="DRV001",
        email="driver@test.com",
        phone="1234567890",
        gender=GenderEnum.MALE,
        password="hashedpassword",
        date_of_birth=date(1990, 1, 1),
        date_of_joining=date(2023, 1, 1),
        license_number="LIC001",
        badge_number="BADGE001",
        bg_verify_status=VerificationStatusEnum.APPROVED,
        is_active=True
    )
    test_db.add(driver)
    test_db.commit()
    test_db.refresh(driver)
    return driver

@pytest.fixture(scope="function")
def test_vehicle(test_db, test_tenant, test_vendor, test_driver):
    """Create a test vehicle with driver"""
    from app.models.vehicle import Vehicle
    from app.models.vehicle_type import VehicleType
    vtype = VehicleType(vehicle_type_id=1, vendor_id=test_vendor.vendor_id, name="Sedan", seats=4)
    test_db.add(vtype)
    test_db.flush()
    vehicle = Vehicle(
        vehicle_id=1,
        vehicle_type_id=1,
        vendor_id=test_vendor.vendor_id,
        rc_number="TEST123",
        driver_id=test_driver.driver_id,
        is_active=True
    )
    test_db.add(vehicle)
    test_db.commit()
    test_db.refresh(vehicle)
    return vehicle

@pytest.fixture(scope="function")
def second_vehicle(test_db, second_tenant, second_vendor):
    """Create vehicle in second tenant"""
    from app.models.vehicle import Vehicle
    from app.models.vehicle_type import VehicleType
    from app.models.driver import Driver, GenderEnum, VerificationStatusEnum
    from datetime import date
    driver = Driver(
        driver_id=2,
        tenant_id=second_tenant.tenant_id,
        vendor_id=second_vendor.vendor_id,
        role_id=2,
        name="Second Driver",
        code="DRV002",
        email="driver2@test.com",
        phone="9876543210",
        gender=GenderEnum.MALE,
        password="hashedpassword",
        date_of_birth=date(1990, 1, 1),
        date_of_joining=date(2023, 1, 1),
        license_number="LIC002",
        badge_number="BADGE002",
        bg_verify_status=VerificationStatusEnum.APPROVED,
        is_active=True
    )
    test_db.add(driver)
    test_db.flush()
    vtype = VehicleType(vehicle_type_id=2, vendor_id=second_vendor.vendor_id, name="SUV", seats=6)
    test_db.add(vtype)
    test_db.flush()
    vehicle = Vehicle(
        vehicle_id=2,
        vehicle_type_id=2,
        vendor_id=second_vendor.vendor_id,
        rc_number="TEST456",
        driver_id=driver.driver_id,
        is_active=True
    )
    test_db.add(vehicle)
    test_db.commit()
    test_db.refresh(vehicle)
    return vehicle

@pytest.fixture(scope="function")
def test_vehicle_no_driver(test_db, test_tenant, test_vendor):
    """Create vehicle without driver"""
    from app.models.vehicle import Vehicle
    from app.models.vehicle_type import VehicleType
    vtype = VehicleType(vehicle_type_id=3, vendor_id=test_vendor.vendor_id, name="Van", seats=8)
    test_db.add(vtype)
    test_db.flush()
    vehicle = Vehicle(
        vehicle_id=3,
        vehicle_type_id=3,
        vendor_id=test_vendor.vendor_id,
        rc_number="TEST789",
        driver_id=None,
        is_active=True
    )
    test_db.add(vehicle)
    test_db.commit()
    test_db.refresh(vehicle)
    return vehicle

@pytest.fixture(scope="function")
def unrouted_booking(test_db, test_tenant, test_shift, test_employee):
    """Create an unrouted booking"""
    from app.models.booking import Booking, BookingStatusEnum
    from datetime import date, timedelta
    tomorrow = date.today() + timedelta(days=1)
    booking = Booking(
        booking_id=2000,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee["employee"].employee_id,
        employee_code=test_employee["employee"].employee_code,
        shift_id=test_shift.shift_id,
        booking_date=tomorrow,
        status=BookingStatusEnum.REQUEST,
        pickup_latitude=40.7128,
        pickup_longitude=-74.0060,
        drop_latitude=40.7580,
        drop_longitude=-73.9855,
        pickup_location="Test Pickup",
        drop_location="Test Drop"
    )
    test_db.add(booking)
    test_db.commit()
    test_db.refresh(booking)
    return booking

@pytest.fixture(scope="function")
def routed_booking(test_db, test_tenant, test_shift, test_employee, test_route):
    """Create a booking already in a route"""
    from app.models.booking import Booking, BookingStatusEnum
    from app.models.route_management import RouteManagementBooking
    from datetime import date, timedelta
    tomorrow = date.today() + timedelta(days=1)
    booking = Booking(
        booking_id=2001,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee["employee"].employee_id,
        employee_code=test_employee["employee"].employee_code,
        shift_id=test_shift.shift_id,
        booking_date=tomorrow,
        status=BookingStatusEnum.SCHEDULED,
        pickup_latitude=40.7128,
        pickup_longitude=-74.0060,
        drop_latitude=40.7580,
        drop_longitude=-73.9855,
        pickup_location="Office",
        drop_location="Home"
    )
    test_db.add(booking)
    test_db.flush()
    route_booking = RouteManagementBooking(
        route_id=test_route.route_id,
        booking_id=booking.booking_id,
        order_id=1,
        estimated_pick_up_time="08:00:00",
        estimated_distance=5.0
    )
    test_db.add(route_booking)
    test_db.commit()
    test_db.refresh(booking)
    return booking

@pytest.fixture(scope="function")
def second_booking(test_db, test_tenant, test_shift, test_employee):
    """Create a second unrouted booking"""
    from app.models.booking import Booking, BookingStatusEnum
    from datetime import date, timedelta
    tomorrow = date.today() + timedelta(days=1)
    booking = Booking(
        booking_id=2002,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee["employee"].employee_id,
        employee_code=test_employee["employee"].employee_code,
        shift_id=test_shift.shift_id,
        booking_date=tomorrow,
        status=BookingStatusEnum.REQUEST,
        pickup_latitude=40.7200,
        pickup_longitude=-74.0100,
        drop_latitude=40.7600,
        drop_longitude=-73.9900,
        pickup_location="Second Pickup",
        drop_location="Second Drop"
    )
    test_db.add(booking)
    test_db.commit()
    test_db.refresh(booking)
    return booking

@pytest.fixture(scope="function")
def test_route(test_db, test_tenant, test_shift, test_vendor):
    """Create a test route with vendor assigned"""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum
    route = RouteManagement(
        route_id=1000,
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift.shift_id,
        route_code="ROUTE001",
        estimated_total_time=60.0,
        estimated_total_distance=10.0,
        buffer_time=5.0,
        status=RouteManagementStatusEnum.PLANNED,
        assigned_vendor_id=test_vendor.vendor_id
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route

@pytest.fixture(scope="function")
def second_route(test_db, second_tenant, second_shift):
    """Create a route in second tenant"""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum
    from app.models.vendor import Vendor
    vendor = Vendor(
        vendor_id=3,
        tenant_id=second_tenant.tenant_id,
        vendor_code="VEND003",
        name="Second Tenant Vendor",
        email="vendor3@test.com",
        phone="5555555555",
        is_active=True
    )
    test_db.add(vendor)
    test_db.flush()
    route = RouteManagement(
        route_id=1001,
        tenant_id=second_tenant.tenant_id,
        shift_id=second_shift.shift_id,
        route_code="ROUTE002",
        estimated_total_time=45.0,
        estimated_total_distance=8.0,
        buffer_time=5.0,
        status=RouteManagementStatusEnum.PLANNED,
        assigned_vendor_id=vendor.vendor_id
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route

@pytest.fixture(scope="function")
def second_route_same_tenant(test_db, test_tenant, test_shift, test_vendor):
    """Create a second route in same tenant"""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum
    route = RouteManagement(
        route_id=1002,
        tenant_id=test_tenant.tenant_id,
        shift_id=test_shift.shift_id,
        route_code="ROUTE003",
        estimated_total_time=50.0,
        estimated_total_distance=9.0,
        buffer_time=5.0,
        status=RouteManagementStatusEnum.PLANNED,
        assigned_vendor_id=test_vendor.vendor_id
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route

@pytest.fixture(scope="function")
def different_shift_route(test_db, test_tenant, second_shift, test_vendor):
    """Create a route with different shift in same tenant"""
    from app.models.route_management import RouteManagement, RouteManagementStatusEnum
    route = RouteManagement(
        route_id=1003,
        tenant_id=test_tenant.tenant_id,
        shift_id=second_shift.shift_id,
        route_code="ROUTE004",
        estimated_total_time=40.0,
        estimated_total_distance=7.0,
        buffer_time=5.0,
        status=RouteManagementStatusEnum.PLANNED,
        assigned_vendor_id=test_vendor.vendor_id
    )
    test_db.add(route)
    test_db.commit()
    test_db.refresh(route)
    return route

@pytest.fixture(scope="function")
def test_booking(test_db, test_tenant, test_shift, test_employee):
    """Create a test booking for status update tests"""
    from app.models.booking import Booking, BookingStatusEnum
    from datetime import date, timedelta
    tomorrow = date.today() + timedelta(days=1)
    booking = Booking(
        booking_id=3000,
        tenant_id=test_tenant.tenant_id,
        employee_id=test_employee["employee"].employee_id,
        employee_code=test_employee["employee"].employee_code,
        shift_id=test_shift.shift_id,
        booking_date=tomorrow,
        status=BookingStatusEnum.REQUEST,
        pickup_latitude=40.7128,
        pickup_longitude=-74.0060,
        drop_latitude=40.7580,
        drop_longitude=-73.9855,
        pickup_location="Test Pickup Location",
        drop_location="Test Drop Location"
    )
    test_db.add(booking)
    test_db.commit()
    test_db.refresh(booking)
    return booking
