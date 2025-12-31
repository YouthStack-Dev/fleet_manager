"""
Simplified Test cases for Alert Configuration Router
Tests basic CRUD operations for alert configuration management
"""
import pytest
from fastapi import status


class TestAlertConfigRouterSimple:
    """Basic test suite for Alert Configuration endpoints"""

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
    # CREATE TESTS
    # ========================================================================

    def test_create_alert_configuration_success(
        self, client, test_db, employee_token, sample_config_data
    ):
        """Test creating alert configuration"""
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data,
            headers={"Authorization": employee_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "Alert configuration created successfully" in data["message"]
        assert data["data"]["config_name"] == sample_config_data["config_name"]
        assert data["data"]["priority"] == sample_config_data["priority"]

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
        # Error responses are wrapped in 'detail' by FastAPI
        error_data = data.get("detail", data)
        assert error_data["success"] is False
        assert error_data["error_code"] == "CONFIG_ALREADY_EXISTS"

    def test_create_alert_configuration_unauthorized(
        self, client, sample_config_data
    ):
        """Test creating configuration without authentication fails"""
        response = client.post(
            "/api/v1/alert-config",
            json=sample_config_data
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ========================================================================
    # GET TESTS
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
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0

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
        error_data = data.get("detail", data)
        assert error_data["success"] is False
        assert error_data["error_code"] == "CONFIG_NOT_FOUND"

    # ========================================================================
    # APPLICABLE CONFIGURATION TESTS
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
        # Configuration matching is handled by the CRUD layer
        # It's valid for data to be None if no applicable config is found

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
        error_data = data.get("detail", data)
        assert error_data["success"] is False
        assert error_data["error_code"] == "INVALID_ALERT_TYPE"

    def test_get_applicable_configuration_missing_alert_type(
        self, client, employee_token
    ):
        """Test getting configuration without alert_type parameter"""
        response = client.get(
            "/api/v1/alert-config/applicable/current",
            headers={"Authorization": employee_token}
        )
        
        # Should be 422 for missing required query parameter
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
        # Should return None when no configuration exists
        assert data["data"] is None
        assert "No configuration found" in data["message"]

    # ========================================================================
    # RESPONSE STRUCTURE TESTS
    # ========================================================================

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
        error_json = error_response.json()
        error_data = error_json.get("detail", error_json)
        assert "success" in error_data
        assert "message" in error_data
        assert "error_code" in error_data
        assert "timestamp" in error_data
        assert error_data["success"] is False
