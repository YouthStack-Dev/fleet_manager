"""
Test cases for Alert Configuration Router
Tests all CRUD operations and permission checks for alert configuration management
"""
import pytest
from fastapi import status
from unittest.mock import Mock, patch


class TestAlertConfigRouter:
    """Test suite for Alert Configuration endpoints"""

    @pytest.fixture
    def sample_config_data(self):
        """Sample alert configuration data"""
        return {
            "config_name": "Emergency Response Team",
            "description": "Primary emergency response configuration",
            "priority": 100,
            "applicable_alert_types": ["SOS", "ACCIDENT", "MEDICAL"],
            "primary_recipients": [
                {
                    "name": "Control Room",
                    "email": "control@example.com",
                    "phone": "+919876543210",
                    "role": "Control Room Operator",
                    "channels": ["SMS", "EMAIL"]
                }
            ],
            "escalation_recipients": [
                {
                    "name": "Manager",
                    "email": "manager@example.com",
                    "phone": "+919876543211",
                    "role": "Transport Manager",
                    "channels": ["EMAIL", "SMS", "PUSH"]
                }
            ],
            "notification_channels": ["SMS", "EMAIL", "PUSH"],
            "enable_escalation": True,
            "escalation_threshold_seconds": 300,
            "notify_on_status_change": True,
            "notify_on_escalation": True,
            "require_closure_notes": True,
            "emergency_contacts": [
                {
                    "name": "Police",
                    "phone": "100",
                    "email": "police@emergency.in",
                    "service_type": "POLICE"
                }
            ]
        }

    # ========================================================================
    # CREATE ALERT CONFIGURATION TESTS
    # ========================================================================

    def test_create_alert_configuration_success_employee(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test creating alert configuration as employee"""
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        if response.status_code != status.HTTP_200_OK:
            print(f"Response: {response.json()}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "Alert configuration created successfully" in data["message"]
        assert data["data"]["config_name"] == sample_config_data["config_name"]
        assert data["data"]["priority"] == sample_config_data["priority"]
        assert data["data"]["is_active"] is True

    def test_create_alert_configuration_success_admin(
        self, client, test_db, admin_token, sample_config_data
    ):
        """Test creating alert configuration as admin with tenant_id"""
        sample_config_data["tenant_id"] = "TEST_TENANT"
        
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["tenant_id"] == "TEST_TENANT"

    def test_create_alert_configuration_duplicate(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test creating duplicate configuration fails"""
        # Create first config
        client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        # Try to create duplicate
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "CONFIG_ALREADY_EXISTS"
        assert "already exists" in data["message"]

    def test_create_alert_configuration_admin_missing_tenant_id(
        self, client, admin_token, sample_config_data
    ):
        """Test admin must provide tenant_id"""
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": admin_token}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "TENANT_ID_REQUIRED"

    def test_create_alert_configuration_unauthorized(
        self, client, sample_config_data
    ):
        """Test creating configuration without authentication fails"""
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_alert_configuration_insufficient_permissions(
        self, client, get_employee_token, sample_config_data
    ):
        """Test creating configuration without proper permissions fails"""
        headers = get_employee_token(permissions=["other.read"])
        
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_alert_configuration_with_team(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test creating team-specific configuration"""
        sample_config_data["team_id"] = 1
        
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["team_id"] == 1

    # ========================================================================
    # GET ALERT CONFIGURATIONS TESTS
    # ========================================================================

    def test_get_alert_configurations_success(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test retrieving all configurations"""
        # Create a config first
        client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        response = client.get(
            "/api/v1/alert-config",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "Retrieved" in data["message"]
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0

    def test_get_alert_configurations_with_team_filter(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test retrieving configurations filtered by team"""
        # Create team-specific config
        sample_config_data["team_id"] = 1
        client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        response = client.get(
            "/api/v1/alert-config?team_id=1",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert all(config.get("team_id") == 1 for config in data["data"] if config.get("team_id"))

    def test_get_alert_configurations_empty(
        self, client, employee_token
    ):
        """Test retrieving configurations when none exist"""
        response = client.get(
            "/api/v1/alert-config",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    # ========================================================================
    # GET SINGLE CONFIGURATION TESTS
    # ========================================================================

    def test_get_alert_configuration_by_id_success(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test retrieving specific configuration by ID"""
        # Create config
        create_response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        config_id = create_response.json()["data"]["config_id"]
        
        # Get config
        response = client.get(
            f"/api/v1/alert-config/{config_id}",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["config_id"] == config_id

    def test_get_alert_configuration_by_id_not_found(
        self, client, employee_token
    ):
        """Test retrieving non-existent configuration"""
        response = client.get(
            "/api/v1/alert-config/99999",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "CONFIG_NOT_FOUND"

    # ========================================================================
    # UPDATE CONFIGURATION TESTS
    # ========================================================================

    def test_update_alert_configuration_success(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test updating alert configuration"""
        # Create config
        create_response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        config_id = create_response.json()["data"]["config_id"]
        
        # Update config
        update_data = {
            "config_name": "Updated Emergency Team",
            "priority": 2
        }
        response = client.put(
            f"/api/v1/alert-config/{config_id}",
            json=update_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["config_name"] == "Updated Emergency Team"
        assert data["data"]["priority"] == 2

    def test_update_alert_configuration_not_found(
        self, client, employee_token
    ):
        """Test updating non-existent configuration"""
        update_data = {"config_name": "Updated Name"}
        
        response = client.put(
            "/api/v1/alert-config/99999",
            json=update_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "CONFIG_NOT_FOUND"

    def test_update_alert_configuration_insufficient_role(
        self, client, get_employee_token, sample_config_data
    ):
        """Test updating configuration without admin role fails"""
        # Create config with admin role
        admin_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="TRANSPORT_MANAGER"
        )
        create_response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=admin_headers
        )
        config_id = create_response.json()["data"]["config_id"]
        
        # Try to update with regular employee
        employee_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="EMPLOYEE"
        )
        
        update_data = {"config_name": "Updated Name"}
        response = client.put(
            f"/api/v1/alert-config/{config_id}",
            json=update_data,
            headers=employee_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ========================================================================
    # DELETE CONFIGURATION TESTS
    # ========================================================================

    def test_delete_alert_configuration_success(
        self, client, test_db, get_employee_token, sample_config_data
    ):
        """Test deleting alert configuration"""
        # Create config
        admin_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="ADMIN"
        )
        create_response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=admin_headers
        )
        config_id = create_response.json()["data"]["config_id"]
        
        # Delete config
        response = client.delete(
            f"/api/v1/alert-config/{config_id}",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["deleted_config_id"] == config_id

    def test_delete_alert_configuration_not_found(
        self, client, get_employee_token
    ):
        """Test deleting non-existent configuration"""
        admin_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="ADMIN"
        )
        
        response = client.delete(
            "/api/v1/alert-config/99999",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "CONFIG_NOT_FOUND"

    def test_delete_alert_configuration_insufficient_role(
        self, client, get_employee_token, sample_config_data
    ):
        """Test deleting configuration without ADMIN role fails"""
        # Create config
        admin_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="ADMIN"
        )
        create_response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=admin_headers
        )
        config_id = create_response.json()["data"]["config_id"]
        
        # Try to delete with non-admin
        manager_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="TRANSPORT_MANAGER"
        )
        
        response = client.delete(
            f"/api/v1/alert-config/{config_id}",
            headers=manager_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "ADMIN_ACCESS_REQUIRED"

    # ========================================================================
    # GET APPLICABLE CONFIGURATION TESTS
    # ========================================================================

    def test_get_applicable_configuration_success(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test getting applicable configuration for alert type"""
        # Create config
        client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        # Get applicable config
        response = client.get(
            "/api/v1/alert-config/applicable/current?alert_type=SOS",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"] is not None
        assert "SOS" in data["data"]["applicable_alert_types"]

    def test_get_applicable_configuration_invalid_alert_type(
        self, client, employee_token
    ):
        """Test getting configuration with invalid alert type"""
        response = client.get(
            "/api/v1/alert-config/applicable/current?alert_type=INVALID_TYPE",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "INVALID_ALERT_TYPE"

    def test_get_applicable_configuration_missing_alert_type(
        self, client, employee_token
    ):
        """Test getting configuration without alert_type parameter"""
        response = client.get(
            "/api/v1/alert-config/applicable/current",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_applicable_configuration_not_found(
        self, client, employee_token
    ):
        """Test getting applicable configuration when none exists"""
        response = client.get(
            "/api/v1/alert-config/applicable/current?alert_type=SOS",
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"] is None
        assert "No configuration found" in data["message"]

    def test_get_applicable_configuration_team_priority(
        self, client, test_db, get_employee_token, sample_config_data
    ):
        """Test that team-specific config takes priority over tenant config"""
        # Create tenant-wide config
        tenant_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="TRANSPORT_MANAGER",
            team_id=None
        )
        sample_config_data["config_name"] = "Tenant Config"
        sample_config_data["priority"] = 1
        client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=tenant_headers
        )
        
        # Create team-specific config
        team_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="TRANSPORT_MANAGER",
            team_id=1
        )
        sample_config_data["config_name"] = "Team Config"
        sample_config_data["team_id"] = 1
        sample_config_data["priority"] = 2
        client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=team_headers
        )
        
        # Get applicable config - should return team config
        response = client.get(
            "/api/v1/alert-config/applicable/current?alert_type=SOS",
            headers=team_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["config_name"] == "Team Config"

    # ========================================================================
    # TEST NOTIFICATION ENDPOINT TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_test_notification_success(
        self, client, test_db, get_employee_token, sample_config_data
    ):
        """Test sending test notifications"""
        admin_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="TRANSPORT_MANAGER",
            employee_id=1
        )
        
        # Create config
        create_response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=admin_headers
        )
        config_id = create_response.json()["data"]["config_id"]
        
        # Send test notification (mock the notification service)
        with patch("app.services.notification_service.NotificationService.notify_alert_triggered") as mock_notify:
            mock_notify.return_value = [Mock(recipient_name="Control Room")]
            
            response = client.post(
                f"/api/v1/alert-config/{config_id}/test-notification",
                headers=admin_headers
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "Test notifications sent successfully" in data["message"]

    def test_test_notification_config_not_found(
        self, client, get_employee_token
    ):
        """Test sending notification for non-existent config"""
        admin_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="TRANSPORT_MANAGER"
        )
        
        response = client.post(
            "/api/v1/alert-config/99999/test-notification",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "CONFIG_NOT_FOUND"

    def test_test_notification_insufficient_role(
        self, client, get_employee_token, sample_config_data
    ):
        """Test sending test notification without admin role fails"""
        # Create config
        admin_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="TRANSPORT_MANAGER"
        )
        create_response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=admin_headers
        )
        config_id = create_response.json()["data"]["config_id"]
        
        # Try to test with regular employee
        employee_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="EMPLOYEE"
        )
        
        response = client.post(
            f"/api/v1/alert-config/{config_id}/test-notification",
            headers=employee_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "ADMIN_ACCESS_REQUIRED"

    # ========================================================================
    # INTEGRATION TESTS
    # ========================================================================

    def test_full_crud_lifecycle(
        self, client, test_db, get_employee_token, sample_config_data
    ):
        """Test complete CRUD lifecycle"""
        admin_headers = get_employee_token(
            permissions=["tenant_config.read", "tenant_config.write"],
            role="ADMIN"
        )
        
        # 1. Create
        create_response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers=admin_headers
        )
        assert create_response.status_code == status.HTTP_200_OK
        config_id = create_response.json()["data"]["config_id"]
        
        # 2. Read single
        get_response = client.get(
            f"/api/v1/alert-config/{config_id}",
            headers=admin_headers
        )
        assert get_response.status_code == status.HTTP_200_OK
        
        # 3. Read list
        list_response = client.get(
            "/api/v1/alert-config",
            headers=admin_headers
        )
        assert list_response.status_code == status.HTTP_200_OK
        assert len(list_response.json()["data"]) >= 1
        
        # 4. Update
        update_response = client.put(
            f"/api/v1/alert-config/{config_id}",
            json={"config_name": "Updated Config"},
            headers=admin_headers
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.json()["data"]["config_name"] == "Updated Config"
        
        # 5. Delete
        delete_response = client.delete(
            f"/api/v1/alert-config/{config_id}",
            headers=admin_headers
        )
        assert delete_response.status_code == status.HTTP_200_OK
        
        # 6. Verify deletion
        verify_response = client.get(
            f"/api/v1/alert-config/{config_id}",
            headers=admin_headers
        )
        assert verify_response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_structure_consistency(
        self, client, employee_token, sample_config_data
    ):
        """Test that all responses follow consistent structure"""
        # Create config
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        # Check success response structure
        data = response.json()
        assert "success" in data
        assert "message" in data
        assert "data" in data
        assert "timestamp" in data
        assert data["success"] is True
        
        # Check error response structure
        error_response = client.get(
            "/api/v1/alert-config/99999",
            headers={"Authorization": employee_token}
        )
        error_data = error_response.json()
        assert "success" in error_data
        assert "message" in error_data
        assert "error_code" in error_data
        assert "timestamp" in error_data
        assert error_data["success"] is False
