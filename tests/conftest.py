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
            module="admin.tenant",
            action="create",
            description="Create tenant"
        ),
        Permission(
            permission_id=2,
            module="admin.tenant",
            action="read",
            description="Read tenant"
        ),
        Permission(
            permission_id=3,
            module="admin.tenant",
            action="update",
            description="Update tenant"
        ),
        Permission(
            permission_id=4,
            module="admin.tenant",
            action="delete",
            description="Delete tenant"
        ),
        Permission(
            permission_id=5,
            module="employee",
            action="read",
            description="Read employee"
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
    role = Role(
        role_id=1,
        tenant_id=None,  # System roles must have NULL tenant_id
        name="SystemAdmin",
        description="System Administrator",
        is_system_role=True,
        is_active=True
    )
    test_db.add(role)
    
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
    role.policies.append(policy)
    
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
        role_id=role.role_id,
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
        "role": role,
        "policy": policy
    }


@pytest.fixture(scope="function")
def employee_user(test_db, seed_permissions):
    """
    Create a regular employee user with limited permissions.
    """
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
    policy.permissions = [seed_permissions[1], seed_permissions[4]]  # tenant.read and employee.read
    
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
def admin_token(admin_user):
    """
    Generate JWT token for admin user.
    """
    token = create_access_token(
        user_id=str(admin_user["employee"].employee_id),
        tenant_id=admin_user["tenant"].tenant_id,
        user_type="admin",
        custom_claims={
            "email": admin_user["employee"].email,
            "permissions": ["admin.tenant.create", "admin.tenant.read", "admin.tenant.update", "admin.tenant.delete"]
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
            "permissions": ["admin.tenant.read", "employee.read"]
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
            "permissions": []
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
