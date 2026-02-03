"""
Test cases for Employee OTP-based login
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.session import get_db
from unittest.mock import MagicMock, patch
import json

client = TestClient(app)


class TestEmployeeOTPLogin:
    """Test suite for OTP-based employee authentication"""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        with patch('common_utils.auth.token_validation.Oauth2AsAccessor') as mock_oauth:
            mock_instance = MagicMock()
            mock_instance.use_redis = True
            mock_redis_client = MagicMock()
            mock_instance.redis_manager.client = mock_redis_client
            mock_oauth.return_value = mock_instance
            yield mock_redis_client
    
    @pytest.fixture
    def mock_email_service(self):
        """Mock Email service"""
        with patch('app.routes.auth_router.EmailService') as mock_email:
            mock_instance = MagicMock()
            mock_instance.send_email.return_value = True
            mock_email.return_value = mock_instance
            yield mock_instance
    
    @pytest.fixture
    def mock_sms_service(self):
        """Mock SMS service"""
        with patch('app.routes.auth_router.SMSService') as mock_sms:
            mock_instance = MagicMock()
            mock_instance.send_sms.return_value = True
            mock_sms.return_value = mock_instance
            yield mock_instance
    
    def test_request_otp_with_email_success(self, mock_redis, mock_email_service, test_employee, test_tenant):
        """Test OTP request with email - single tenant"""
        response = client.post(
            "/auth/employee/request-otp",
            json={
                "username": test_employee.email,
                "tenant_id": str(test_tenant.tenant_id)
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["otp_sent"] is True
        assert data["data"]["delivery_channel"] == "email"
        assert data["data"]["expires_in"] == 300
        assert data["data"]["max_attempts"] == 3
    
    def test_request_otp_with_phone_success(self, mock_redis, mock_sms_service, test_employee, test_tenant):
        """Test OTP request with phone number - single tenant"""
        response = client.post(
            "/auth/employee/request-otp",
            json={
                "username": test_employee.phone,
                "tenant_id": str(test_tenant.tenant_id)
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["otp_sent"] is True
        assert data["data"]["delivery_channel"] == "sms"
    
    def test_request_otp_multiple_tenants(self, mock_redis, test_db):
        """Test OTP request returns tenant list when multiple tenants found"""
        # Create employee with same email in multiple tenants
        # (Setup test data with duplicate email across tenants)
        
        response = client.post(
            "/auth/employee/request-otp",
            json={
                "username": "duplicate@example.com"
            }
        )
        
        data = response.json()
        if "multiple_tenants" in data.get("data", {}):
            assert data["success"] is True
            assert data["data"]["multiple_tenants"] is True
            assert len(data["data"]["tenants"]) > 1
            assert "tenant_id" in data["data"]["tenants"][0]
            assert "name" in data["data"]["tenants"][0]
    
    def test_request_otp_invalid_email_format(self):
        """Test OTP request with invalid email format"""
        response = client.post(
            "/auth/employee/request-otp",
            json={
                "username": "invalid-email",
                "tenant_id": "test-tenant"
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_request_otp_invalid_phone_format(self):
        """Test OTP request with invalid phone format"""
        response = client.post(
            "/auth/employee/request-otp",
            json={
                "username": "123",  # Too short
                "tenant_id": "test-tenant"
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_request_otp_employee_not_found(self, mock_redis):
        """Test OTP request for non-existent employee"""
        response = client.post(
            "/auth/employee/request-otp",
            json={
                "username": "nonexistent@example.com",
                "tenant_id": "test-tenant"
            }
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "EMPLOYEE_NOT_FOUND"
    
    def test_request_otp_inactive_account(self, mock_redis, test_employee, test_tenant):
        """Test OTP request for inactive employee"""
        # Set employee as inactive
        test_employee.is_active = False
        
        response = client.post(
            "/auth/employee/request-otp",
            json={
                "username": test_employee.email,
                "tenant_id": str(test_tenant.tenant_id)
            }
        )
        
        assert response.status_code == 403
        data = response.json()
        assert data["error_code"] == "ACCOUNT_INACTIVE"
    
    def test_verify_otp_success(self, mock_redis, mock_email_service, test_employee, test_tenant):
        """Test successful OTP verification"""
        # Step 1: Request OTP
        request_response = client.post(
            "/auth/employee/request-otp",
            json={
                "username": test_employee.email,
                "tenant_id": str(test_tenant.tenant_id)
            }
        )
        assert request_response.status_code == 200
        
        # Mock Redis to return valid OTP
        otp = "123456"
        otp_data = {
            "otp": otp,
            "employee_id": str(test_employee.employee_id),
            "attempts": 0,
            "max_attempts": 3,
            "created_at": 1234567890
        }
        mock_redis.get.return_value = json.dumps(otp_data).encode()
        
        # Step 2: Verify OTP
        verify_response = client.post(
            "/auth/employee/verify-otp",
            json={
                "username": test_employee.email,
                "tenant_id": str(test_tenant.tenant_id),
                "otp": otp
            }
        )
        
        assert verify_response.status_code == 200
        data = verify_response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert "user" in data["data"]
        assert "employee" in data["data"]["user"]
        assert "roles" in data["data"]["user"]
        assert "permissions" in data["data"]["user"]
    
    def test_verify_otp_expired(self, mock_redis):
        """Test OTP verification with expired OTP"""
        mock_redis.get.return_value = None
        
        response = client.post(
            "/auth/employee/verify-otp",
            json={
                "username": "test@example.com",
                "tenant_id": "test-tenant",
                "otp": "123456"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "OTP_EXPIRED"
    
    def test_verify_otp_invalid(self, mock_redis, test_employee, test_tenant):
        """Test OTP verification with wrong OTP"""
        otp_data = {
            "otp": "123456",
            "employee_id": str(test_employee.employee_id),
            "attempts": 0,
            "max_attempts": 3,
            "created_at": 1234567890
        }
        mock_redis.get.return_value = json.dumps(otp_data).encode()
        mock_redis.ttl.return_value = 200
        
        response = client.post(
            "/auth/employee/verify-otp",
            json={
                "username": test_employee.email,
                "tenant_id": str(test_tenant.tenant_id),
                "otp": "999999"  # Wrong OTP
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "INVALID_OTP"
        assert "remaining_attempts" in data.get("details", {})
    
    def test_verify_otp_max_attempts_exceeded(self, mock_redis, test_employee, test_tenant):
        """Test OTP verification after max attempts"""
        otp_data = {
            "otp": "123456",
            "employee_id": str(test_employee.employee_id),
            "attempts": 3,  # Already at max
            "max_attempts": 3,
            "created_at": 1234567890
        }
        mock_redis.get.return_value = json.dumps(otp_data).encode()
        
        response = client.post(
            "/auth/employee/verify-otp",
            json={
                "username": test_employee.email,
                "tenant_id": str(test_tenant.tenant_id),
                "otp": "123456"
            }
        )
        
        assert response.status_code == 429
        data = response.json()
        assert data["error_code"] == "MAX_OTP_ATTEMPTS"
    
    def test_verify_otp_invalid_format(self):
        """Test OTP verification with invalid OTP format"""
        response = client.post(
            "/auth/employee/verify-otp",
            json={
                "username": "test@example.com",
                "tenant_id": "test-tenant",
                "otp": "12345"  # Only 5 digits
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_verify_otp_non_numeric(self):
        """Test OTP verification with non-numeric OTP"""
        response = client.post(
            "/auth/employee/verify-otp",
            json={
                "username": "test@example.com",
                "tenant_id": "test-tenant",
                "otp": "ABCDEF"  # Letters instead of numbers
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_otp_single_session_enforcement(self, mock_redis, mock_email_service, test_employee, test_tenant):
        """Test that new OTP login invalidates previous session"""
        # First login
        otp1 = "123456"
        otp_data1 = {
            "otp": otp1,
            "employee_id": str(test_employee.employee_id),
            "attempts": 0,
            "max_attempts": 3,
            "created_at": 1234567890
        }
        mock_redis.get.return_value = json.dumps(otp_data1).encode()
        
        response1 = client.post(
            "/auth/employee/verify-otp",
            json={
                "username": test_employee.email,
                "tenant_id": str(test_tenant.tenant_id),
                "otp": otp1
            }
        )
        
        assert response1.status_code == 200
        token1 = response1.json()["data"]["access_token"]
        
        # Second login (should invalidate first)
        otp2 = "654321"
        otp_data2 = {
            "otp": otp2,
            "employee_id": str(test_employee.employee_id),
            "attempts": 0,
            "max_attempts": 3,
            "created_at": 1234567891
        }
        mock_redis.get.return_value = json.dumps(otp_data2).encode()
        
        response2 = client.post(
            "/auth/employee/verify-otp",
            json={
                "username": test_employee.email,
                "tenant_id": str(test_tenant.tenant_id),
                "otp": otp2
            }
        )
        
        assert response2.status_code == 200
        token2 = response2.json()["data"]["access_token"]
        assert token1 != token2
        
        # Verify that old session key was deleted
        mock_redis.delete.assert_called()
