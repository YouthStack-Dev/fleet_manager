import pytest
from fastapi import status
from fastapi.testclient import TestClient
from io import BytesIO
import openpyxl
from main import app
from app.database.session import get_db
from app.models.employee import Employee
from app.models.team import Team
from app.models.tenant import Tenant
from sqlalchemy.orm import Session

client = TestClient(app)


def create_test_excel(data_rows: list, headers: list = None) -> BytesIO:
    """
    Create an Excel file for testing.
    
    Args:
        data_rows: List of dictionaries with employee data
        headers: Optional custom headers (default: standard employee headers)
    
    Returns:
        BytesIO object containing the Excel file
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    
    # Default headers
    if headers is None:
        headers = ['name', 'email', 'phone', 'employee_code', 'team_id', 
                   'address', 'latitude', 'longitude', 'gender', 'password']
    
    # Write headers
    ws.append(headers)
    
    # Write data rows
    for row_data in data_rows:
        row = []
        for header in headers:
            row.append(row_data.get(header, ''))
        ws.append(row)
    
    # Save to BytesIO
    excel_buffer = BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)
    
    return excel_buffer


class TestBulkEmployeeCreation:
    """Test suite for bulk employee creation endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self, test_db, admin_user):
        """Setup test data before each test"""
        self.db = test_db
        self.admin_user = admin_user
        
        # Create test tenant
        self.test_tenant = Tenant(
            tenant_id="TEST001",
            name="Test Company",
            address="Test Address",
            latitude=12.9716,
            longitude=77.5946
        )
        test_db.add(self.test_tenant)
        
        # Create test team
        self.test_team = Team(
            name="Test Team",
            tenant_id="TEST001"
        )
        test_db.add(self.test_team)
        test_db.commit()
        test_db.refresh(self.test_team)
        
        # Override the database dependency for the app
        def override_get_db():
            try:
                yield test_db
            finally:
                pass
        
        app.dependency_overrides[get_db] = override_get_db
        
        yield
        
        # Cleanup
        test_db.query(Employee).filter(Employee.tenant_id == "TEST001").delete()
        test_db.query(Team).filter(Team.tenant_id == "TEST001").delete()
        test_db.query(Tenant).filter(Tenant.tenant_id == "TEST001").delete()
        test_db.commit()
        app.dependency_overrides.clear()
    
    def get_auth_headers(self, admin_token):
        """Get authentication headers for testing"""
        return {
            "Authorization": f"Bearer {admin_token}"
        }
    
    def test_bulk_upload_success(self, admin_token):
        """Test successful bulk employee creation"""
        # Prepare test data
        employees = [
            {
                'name': 'John Doe',
                'email': 'john.doe@test.com',
                'phone': '+1234567890',
                'employee_code': 'EMP001',
                'team_id': str(self.test_team.team_id),
                'address': '123 Main St',
                'latitude': '12.9716',
                'longitude': '77.5946',
                'gender': 'Male',
                'password': 'Test@123'
            },
            {
                'name': 'Jane Smith',
                'email': 'jane.smith@test.com',
                'phone': '+1234567891',
                'employee_code': 'EMP002',
                'team_id': str(self.test_team.team_id),
                'address': '456 Oak Ave',
                'gender': 'Female',
            },
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['success'] == True
        assert data['data']['successful'] == 2
        assert data['data']['failed'] == 0
        assert len(data['data']['created_employees']) == 2
    
    def test_bulk_upload_invalid_file_format(self, admin_token):
        """Test rejection of invalid file format"""
        # Create a text file instead of Excel
        text_file = BytesIO(b"Not an Excel file")
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.txt", text_file, "text/plain")},
            headers=self.get_auth_headers(admin_token)
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'Invalid file format' in data['error']['message']
    
    def test_bulk_upload_missing_required_columns(self, admin_token):
        """Test validation of missing required columns"""
        # Excel with missing 'email' column
        headers = ['name', 'phone', 'team_id']
        employees = [
            {'name': 'John Doe', 'phone': '+1234567890', 'team_id': '1'}
        ]
        
        excel_file = create_test_excel(employees, headers=headers)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'Missing required columns' in data['error']['message']
        assert 'email' in data['error']['message']
    
    def test_bulk_upload_invalid_email(self, admin_token):
        """Test validation of invalid email format"""
        employees = [
            {
                'name': 'John Doe',
                'email': 'invalid-email',  # Invalid email
                'phone': '+1234567890',
                'team_id': str(self.test_team.team_id)
            }
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['success'] == False
        assert 'Validation failed' in data['error']['message']
        assert len(data['error']['data']['errors']) > 0
        assert 'Invalid email format' in str(data['error']['data']['errors'])
    
    def test_bulk_upload_invalid_phone(self, admin_token):
        """Test validation of invalid phone format"""
        employees = [
            {
                'name': 'John Doe',
                'email': 'john@test.com',
                'phone': '123',  # Too short
                'team_id': str(self.test_team.team_id)
            }
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['success'] == False
        assert 'Invalid phone format' in str(data['error']['data']['errors'])
    
    def test_bulk_upload_duplicate_email_in_db(self, admin_token):
        """Test handling of duplicate email that exists in database"""
        # Create existing employee
        existing_emp = Employee(
            name="Existing User",
            email="existing@test.com",
            phone="+9999999999",
            tenant_id="TEST001",
            team_id=self.test_team.team_id,
            password="hashed"
        )
        self.db.add(existing_emp)
        self.db.commit()
        
        # Try to create with same email
        employees = [
            {
                'name': 'New User',
                'email': 'existing@test.com',  # Duplicate
                'phone': '+1234567890',
                'team_id': str(self.test_team.team_id)
            }
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers(admin_token)
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'already exists' in str(data['error']['data']['errors']).lower()
    
    def test_bulk_upload_invalid_team_id(self, admin_token):
        """Test validation of non-existent team ID"""
        employees = [
            {
                'name': 'John Doe',
                'email': 'john@test.com',
                'phone': '+1234567890',
                'team_id': '99999'  # Non-existent team
            }
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'does not exist' in str(data['error']['data']['errors'])
    
    def test_bulk_upload_invalid_coordinates(self, admin_token):
        """Test validation of invalid latitude/longitude"""
        employees = [
            {
                'name': 'John Doe',
                'email': 'john@test.com',
                'phone': '+1234567890',
                'team_id': str(self.test_team.team_id),
                'latitude': '200',  # Invalid (> 90)
                'longitude': 'invalid'  # Invalid format
            }
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        errors_str = str(data['error']['data']['errors'])
        assert 'latitude' in errors_str.lower() or 'longitude' in errors_str.lower()
    
    def test_bulk_upload_empty_file(self, admin_token):
        """Test handling of empty Excel file"""
        employees = []  # No data rows
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'No valid data' in data['error']['message']
    
    def test_bulk_upload_too_many_rows(self, admin_token):
        """Test rejection of files with too many rows"""
        # Create 501 rows (exceeds limit of 500)
        employees = []
        for i in range(501):
            employees.append({
                'name': f'Employee {i}',
                'email': f'emp{i}@test.com',
                'phone': f'+123456{i:04d}',
                'team_id': str(self.test_team.team_id)
            })
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'Too many rows' in data['error']['message']
    
    def test_bulk_upload_partial_success(self, admin_token):
        """Test partial success when some rows are valid and some are not"""
        employees = [
            {
                'name': 'Valid User 1',
                'email': 'valid1@test.com',
                'phone': '+1234567890',
                'team_id': str(self.test_team.team_id)
            },
            {
                'name': 'Invalid User',
                'email': 'invalid-email',  # Invalid
                'phone': '+1234567891',
                'team_id': str(self.test_team.team_id)
            },
            {
                'name': 'Valid User 2',
                'email': 'valid2@test.com',
                'phone': '+1234567892',
                'team_id': str(self.test_team.team_id)
            }
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers()
        )
        
        # Should return validation errors, no employees created
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['success'] == False
        assert 'Validation failed' in data['error']['message']
    
    def test_bulk_upload_skip_empty_rows(self, admin_token):
        """Test that empty rows are properly skipped"""
        employees = [
            {
                'name': 'John Doe',
                'email': 'john@test.com',
                'phone': '+1234567890',
                'team_id': str(self.test_team.team_id)
            },
            {},  # Empty row
            {
                'name': 'Jane Smith',
                'email': 'jane@test.com',
                'phone': '+1234567891',
                'team_id': str(self.test_team.team_id)
            }
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers(admin_token)
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['success'] == True
        assert data['data']['successful'] == 2  # Only 2 valid rows
    
    def test_bulk_upload_vendor_forbidden(self, admin_token):
        """Test that vendors cannot perform bulk upload"""
        employees = [
            {
                'name': 'John Doe',
                'email': 'john@test.com',
                'phone': '+1234567890',
                'team_id': str(self.test_team.team_id)
            }
        ]
        
        excel_file = create_test_excel(employees)
        
        response = client.post(
            "/api/v1/employees/bulk-upload",
            files={"file": ("employees.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=self.get_auth_headers(user_type="vendor")
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert 'permission' in data['error']['message'].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
