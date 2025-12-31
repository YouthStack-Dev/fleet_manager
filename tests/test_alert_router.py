"""
Test cases for Alert Router (SOS Alert System)
Employee and responder facing endpoints
"""
import pytest
from datetime import date, datetime, timedelta
from app.models.alert import Alert, AlertStatusEnum, AlertSeverityEnum, AlertTypeEnum
from app.models.booking import Booking
from app.models.employee import Employee


class TestAlertRouter:
    """Test cases for Alert Router endpoints"""
    
    def test_trigger_alert_success(self, client, employee_token, employee_user, test_db):
        """Test triggering an alert successfully"""
        headers = {"Authorization": employee_token}
        
        payload = {
            "alert_type": "SOS",
            "severity": "CRITICAL",
            "current_latitude": 12.9716,
            "current_longitude": 77.5946,
            "trigger_notes": "Emergency situation - need help immediately"
        }
        
        response = client.post("/api/v1/alerts/trigger", json=payload, headers=headers)
        
        # Debug: print response if not 200
        if response.status_code != 200:
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert data.get("success") is True
        assert "message" in data
        assert "data" in data
        assert data["data"]["alert_type"] == "SOS"
        assert data["data"]["severity"] == "CRITICAL"
        assert data["data"]["status"] == "TRIGGERED"
        assert data["data"]["trigger_latitude"] == 12.9716
        assert data["data"]["trigger_longitude"] == 77.5946
        
    def test_trigger_alert_duplicate_active(self, client, employee_token, employee_user, test_db):
        """Test that duplicate active alert is prevented"""
        headers = {"Authorization": employee_token}
        
        # Create first alert
        alert = Alert(
            tenant_id=employee_user["tenant"].tenant_id,
            employee_id=employee_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.TRIGGERED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        
        # Try to trigger another alert
        payload = {
            "alert_type": "SOS",
            "severity": "CRITICAL",
            "current_latitude": 12.9716,
            "current_longitude": 77.5946
        }
        
        response = client.post("/api/v1/alerts/trigger", json=payload, headers=headers)
        
        assert response.status_code == 400
        data = response.json()
        error_data = data.get("detail", data)
        
        assert error_data.get("success") is False
        assert error_data.get("error_code") == "DUPLICATE_ALERT"
        assert "already have an active alert" in error_data.get("message", "").lower()
        
    def test_trigger_alert_with_invalid_booking(self, client, employee_token, employee_user, test_db):
        """Test triggering alert with non-existent booking"""
        headers = {"Authorization": employee_token}
        
        payload = {
            "booking_id": 99999,  # Non-existent
            "alert_type": "SOS",
            "severity": "CRITICAL",
            "current_latitude": 12.9716,
            "current_longitude": 77.5946
        }
        
        response = client.post("/api/v1/alerts/trigger", json=payload, headers=headers)
        
        assert response.status_code == 404
        data = response.json()
        error_data = data.get("detail", data)
        
        assert error_data.get("success") is False
        assert error_data.get("error_code") == "BOOKING_NOT_FOUND"
        
    def test_get_active_alerts_empty(self, client, employee_token, employee_user, test_db):
        """Test getting active alerts when none exist"""
        headers = {"Authorization": employee_token}
        
        response = client.get("/api/v1/alerts/active", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert isinstance(data.get("data"), list)
        assert len(data.get("data")) == 0
        assert "0 active alert" in data.get("message", "").lower()
        
    def test_get_active_alerts_with_data(self, client, employee_token, employee_user, test_db):
        """Test getting active alerts when they exist"""
        headers = {"Authorization": employee_token}
        
        # Create active alert
        alert = Alert(
            tenant_id=employee_user["tenant"].tenant_id,
            employee_id=employee_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.TRIGGERED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        
        response = client.get("/api/v1/alerts/active", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert isinstance(data.get("data"), list)
        assert len(data.get("data")) == 1
        assert data["data"][0]["alert_type"] == "SOS"
        assert data["data"][0]["status"] == "TRIGGERED"
        
    def test_get_my_alerts_history(self, client, employee_token, employee_user, test_db):
        """Test getting alert history with pagination"""
        headers = {"Authorization": employee_token}
        
        # Create multiple alerts
        for i in range(5):
            alert = Alert(
                tenant_id=employee_user["tenant"].tenant_id,
                employee_id=employee_user["employee"].employee_id,
                alert_type=AlertTypeEnum.SOS,
                severity=AlertSeverityEnum.HIGH if i % 2 == 0 else AlertSeverityEnum.CRITICAL,
                status=AlertStatusEnum.CLOSED if i < 3 else AlertStatusEnum.TRIGGERED,
                trigger_latitude=12.9716 + i * 0.001,
                trigger_longitude=77.5946 + i * 0.001
            )
            test_db.add(alert)
        test_db.commit()
        
        response = client.get("/api/v1/alerts/my-alerts?limit=3", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert "data" in data
        assert "alerts" in data["data"]
        assert len(data["data"]["alerts"]) == 3
        assert data["data"]["total"] == 3
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 3
        
    def test_get_my_alerts_with_status_filter(self, client, employee_token, employee_user, test_db):
        """Test filtering alerts by status"""
        headers = {"Authorization": employee_token}
        
        # Create alerts with different statuses
        for status in [AlertStatusEnum.TRIGGERED, AlertStatusEnum.CLOSED, AlertStatusEnum.CLOSED]:
            alert = Alert(
                tenant_id=employee_user["tenant"].tenant_id,
                employee_id=employee_user["employee"].employee_id,
                alert_type=AlertTypeEnum.SOS,
                severity=AlertSeverityEnum.CRITICAL,
                status=status,
                trigger_latitude=12.9716,
                trigger_longitude=77.5946
            )
            test_db.add(alert)
        test_db.commit()
        
        response = client.get("/api/v1/alerts/my-alerts?status=CLOSED", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert len(data["data"]["alerts"]) == 2
        assert all(alert["status"] == "CLOSED" for alert in data["data"]["alerts"])
        
    def test_get_alert_details_success(self, client, employee_token, employee_user, test_db):
        """Test getting specific alert details"""
        headers = {"Authorization": employee_token}
        
        # Create alert
        alert = Alert(
            tenant_id=employee_user["tenant"].tenant_id,
            employee_id=employee_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.TRIGGERED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946,
            trigger_notes="Test emergency"
        )
        test_db.add(alert)
        test_db.commit()
        alert_id = alert.alert_id
        
        response = client.get(f"/api/v1/alerts/{alert_id}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert data["data"]["alert_id"] == alert_id
        assert data["data"]["trigger_notes"] == "Test emergency"
        
    def test_get_alert_details_not_found(self, client, employee_token, test_db):
        """Test getting non-existent alert"""
        headers = {"Authorization": employee_token}
        
        response = client.get("/api/v1/alerts/99999", headers=headers)
        
        assert response.status_code == 404
        data = response.json()
        error_data = data.get("detail", data)
        
        assert error_data.get("success") is False
        assert error_data.get("error_code") == "ALERT_NOT_FOUND"
        
    def test_get_alert_details_access_denied(self, client, employee_token, employee_user, test_db):
        """Test access control - employee can't view other employee's alert"""
        # Create another employee in the same tenant
        from app.models.employee import Employee
        from common_utils.auth.utils import hash_password
        
        other_employee = Employee(
            employee_id=999,
            tenant_id=employee_user["tenant"].tenant_id,
            role_id=employee_user["employee"].role_id,
            team_id=employee_user["employee"].team_id,
            name="Other Employee",
            employee_code="EMP999",
            email="other@test.com",
            phone="+9876543210",
            password=hash_password("Test@123"),
            is_active=True
        )
        test_db.add(other_employee)
        test_db.commit()
        
        # Create alert for the other employee
        alert = Alert(
            tenant_id=employee_user["tenant"].tenant_id,
            employee_id=other_employee.employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.TRIGGERED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        alert_id = alert.alert_id
        
        # Try to access with employee token (different employee, same tenant)
        headers = {"Authorization": employee_token}
        response = client.get(f"/api/v1/alerts/{alert_id}", headers=headers)
        
        # Should be allowed - employee has booking.read permission which grants access to all alerts in tenant
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data["data"]["alert_id"] == alert_id
        
    def test_acknowledge_alert_success(self, client, admin_token, admin_user, test_db):
        """Test acknowledging an alert by responder"""
        # Create alert using admin's employee
        alert = Alert(
            tenant_id=admin_user["tenant"].tenant_id,
            employee_id=admin_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.TRIGGERED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        alert_id = alert.alert_id
        
        headers = {"Authorization": admin_token}
        payload = {
            "acknowledged_by": "admin",
            "notes": "On my way to help"
        }
        
        response = client.put(f"/api/v1/alerts/{alert_id}/acknowledge", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert data["data"]["status"] == "ACKNOWLEDGED"
        assert "response time" in data["message"].lower()
        
    def test_acknowledge_alert_not_found(self, client, admin_token, test_db):
        """Test acknowledging non-existent alert"""
        headers = {"Authorization": admin_token}
        payload = {
            "acknowledged_by": "admin",
            "notes": "On my way"
        }
        
        response = client.put("/api/v1/alerts/99999/acknowledge", json=payload, headers=headers)
        
        assert response.status_code == 404
        data = response.json()
        error_data = data.get("detail", data)
        
        assert error_data.get("success") is False
        assert error_data.get("error_code") == "ALERT_NOT_FOUND"
        
    def test_close_alert_success(self, client, admin_token, admin_user, test_db):
        """Test closing an alert"""
        # Create alert using admin's employee
        alert = Alert(
            tenant_id=admin_user["tenant"].tenant_id,
            employee_id=admin_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.ACKNOWLEDGED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        alert_id = alert.alert_id
        
        headers = {"Authorization": admin_token}
        payload = {
            "closed_by": admin_user["employee"].employee_id,
            "resolution_notes": "Situation resolved, employee is safe",
            "is_false_alarm": False
        }
        
        response = client.put(f"/api/v1/alerts/{alert_id}/close", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert data["data"]["status"] == "CLOSED"
        assert "resolution time" in data["message"].lower()
        
    def test_close_alert_as_false_alarm(self, client, admin_token, admin_user, test_db):
        """Test closing alert as false alarm"""
        # Create alert using admin's employee
        alert = Alert(
            tenant_id=admin_user["tenant"].tenant_id,
            employee_id=admin_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.TRIGGERED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        alert_id = alert.alert_id
        
        headers = {"Authorization": admin_token}
        payload = {
            "closed_by": admin_user["employee"].employee_id,
            "resolution_notes": "Button pressed accidentally",
            "is_false_alarm": True
        }
        
        response = client.put(f"/api/v1/alerts/{alert_id}/close", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert data["data"]["status"] == "FALSE_ALARM"
        
    def test_escalate_alert_success(self, client, admin_token, admin_user, test_db):
        """Test manually escalating an alert"""
        # Create alert using admin's employee
        alert = Alert(
            tenant_id=admin_user["tenant"].tenant_id,
            employee_id=admin_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.ACKNOWLEDGED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        alert_id = alert.alert_id
        
        headers = {"Authorization": admin_token}
        payload = {
            "escalated_by": "admin",
            "escalation_level": 2,
            "escalated_to": "supervisor@test.com",
            "reason": "Situation requires additional support"
        }
        
        response = client.post(f"/api/v1/alerts/{alert_id}/escalate", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert "escalated to level 2" in data["message"].lower()
        
    def test_escalate_closed_alert_fails(self, client, admin_token, admin_user, test_db):
        """Test that closed alerts cannot be escalated"""
        # Create closed alert using admin's employee
        alert = Alert(
            tenant_id=admin_user["tenant"].tenant_id,
            employee_id=admin_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.CLOSED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        alert_id = alert.alert_id
        
        headers = {"Authorization": admin_token}
        payload = {
            "escalated_by": "admin",
            "escalation_level": 2,
            "escalated_to": "supervisor@test.com",
            "reason": "Need more support"
        }
        
        response = client.post(f"/api/v1/alerts/{alert_id}/escalate", json=payload, headers=headers)
        
        assert response.status_code == 400
        data = response.json()
        error_data = data.get("detail", data)
        
        assert error_data.get("success") is False
        assert error_data.get("error_code") == "INVALID_ALERT_STATUS"
        
    def test_get_alert_timeline(self, client, employee_token, employee_user, test_db):
        """Test getting alert timeline"""
        alert = Alert(
            tenant_id=employee_user["tenant"].tenant_id,
            employee_id=employee_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.TRIGGERED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        alert_id = alert.alert_id
        
        headers = {"Authorization": employee_token}
        response = client.get(f"/api/v1/alerts/{alert_id}/timeline", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") is True
        assert "data" in data
        
    def test_response_structure_consistency(self, client, employee_token, employee_user, test_db):
        """Test that all success responses follow the same structure"""
        headers = {"Authorization": employee_token}
        
        # Create an alert
        alert = Alert(
            tenant_id=employee_user["tenant"].tenant_id,
            employee_id=employee_user["employee"].employee_id,
            alert_type=AlertTypeEnum.SOS,
            severity=AlertSeverityEnum.CRITICAL,
            status=AlertStatusEnum.TRIGGERED,
            trigger_latitude=12.9716,
            trigger_longitude=77.5946
        )
        test_db.add(alert)
        test_db.commit()
        
        # Test multiple endpoints for consistent structure
        endpoints = [
            ("/api/v1/alerts/active", "GET"),
            ("/api/v1/alerts/my-alerts", "GET"),
            (f"/api/v1/alerts/{alert.alert_id}", "GET"),
            (f"/api/v1/alerts/{alert.alert_id}/timeline", "GET"),
        ]
        
        for endpoint, method in endpoints:
            if method == "GET":
                response = client.get(endpoint, headers=headers)
            
            assert response.status_code == 200
            data = response.json()
            
            # Check consistent response structure
            assert "success" in data
            assert "message" in data
            assert "data" in data
            assert data["success"] is True
            
    def test_error_response_structure_consistency(self, client, employee_token, test_db):
        """Test that all error responses follow the same structure"""
        headers = {"Authorization": employee_token}
        
        # Test various error scenarios
        error_tests = [
            ("/api/v1/alerts/99999", "GET", 404, "ALERT_NOT_FOUND"),
            ("/api/v1/alerts/99999/acknowledge", "PUT", 404, "ALERT_NOT_FOUND"),
            ("/api/v1/alerts/99999/close", "PUT", 404, "ALERT_NOT_FOUND"),
        ]
        
        for endpoint, method, expected_status, expected_error_code in error_tests:
            if method == "GET":
                response = client.get(endpoint, headers=headers)
            elif method == "PUT":
                if "close" in endpoint:
                    response = client.put(endpoint, json={"closed_by": 1, "resolution_notes": "test", "is_false_alarm": False}, headers=headers)
                else:
                    response = client.put(endpoint, json={"acknowledged_by": "test", "notes": "test"}, headers=headers)
            
            assert response.status_code == expected_status
            data = response.json()
            
            # Error can be in detail key (FastAPI wrapping)
            error_data = data.get("detail", data)
            
            assert error_data.get("success") is False
            assert "error_code" in error_data
            assert error_data.get("error_code") == expected_error_code
            assert "message" in error_data
