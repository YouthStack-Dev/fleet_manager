# Vendor User API - Frontend Documentation

## Base URL
```
/api/v1/vendor-users
```

## Authentication
All endpoints require authentication token in the header:
```
Authorization: Bearer <your_access_token>
```

## Important Notes for Frontend Developers

### Tenant ID Handling
- **Admin Users**: Must provide `tenant_id` in request body (for POST) or as query parameter (for GET/PUT/PATCH)
- **Employee Users**: `tenant_id` is automatically extracted from the authentication token

---

## Endpoints

### 1. Create Vendor User
**POST** `/api/v1/vendor-users/`

Creates a new vendor user for a specific vendor.

#### Request Body
```json
{
  "name": "John Doe",
  "email": "john.doe@example.com",
  "phone": "+1234567890",
  "vendor_id": 1,
  "tenant_id": "SAM001",  // Required for Admin, ignored for Employee
  "role_id": 5,           // Optional - IAM role ID
  "password": "SecurePass123!",
  "is_active": true
}
```

#### Validation Rules
- **name**: 2-50 characters, letters, spaces, hyphens, and apostrophes only
- **email**: Valid email format (validated by Pydantic)
- **phone**: E.164 format (e.g., +1234567890)
- **password**: Minimum 8 characters with at least:
  - One uppercase letter
  - One lowercase letter
  - One number
  - One special character (@$!%*?&)

#### Success Response (201 Created)
```json
{
  "success": true,
  "message": "Vendor user created successfully",
  "data": {
    "vendor_user_id": 1,
    "tenant_id": "SAM001",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "phone": "+1234567890",
    "vendor_id": 1,
    "role_id": 5,
    "is_active": true,
    "created_at": "2025-11-26T12:00:00",
    "updated_at": "2025-11-26T12:00:00"
  },
  "error_code": null,
  "details": null,
  "timestamp": "2025-11-26 12:00:00"
}
```

#### Error Responses

**400 - Tenant ID Required (Admin)**
```json
{
  "detail": {
    "success": false,
    "message": "Tenant ID is required in request body for admin",
    "error_code": "TENANT_ID_REQUIRED"
  }
}
```

**403 - Tenant ID Missing (Employee)**
```json
{
  "detail": {
    "success": false,
    "message": "Tenant ID missing in token for employee",
    "error_code": "TENANT_ID_REQUIRED"
  }
}
```

**404 - Vendor Not Found**
```json
{
  "detail": {
    "success": false,
    "message": "Vendor with ID 1 not found",
    "error_code": "VENDOR_NOT_FOUND"
  }
}
```

**400 - Duplicate Email**
```json
{
  "detail": {
    "success": false,
    "message": "Email 'john.doe@example.com' already exists in this tenant",
    "error_code": "DUPLICATE_EMAIL"
  }
}
```

**400 - Duplicate Phone**
```json
{
  "detail": {
    "success": false,
    "message": "Phone '+1234567890' already exists in this tenant",
    "error_code": "DUPLICATE_PHONE"
  }
}
```

**403 - Vendor Tenant Mismatch**
```json
{
  "detail": {
    "success": false,
    "message": "Vendor does not belong to your tenant",
    "error_code": "VENDOR_TENANT_MISMATCH"
  }
}
```

---

### 2. Get All Vendor Users (List with Pagination)
**GET** `/api/v1/vendor-users/`

Retrieves a paginated list of vendor users with optional filtering.

#### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | Yes (Admin) | Tenant ID - Required for Admin, automatic for Employee |
| `skip` | integer | No | Number of records to skip (default: 0) |
| `limit` | integer | No | Maximum records to return (default: 100, max: 1000) |
| `name` | string | No | Filter by name (case-insensitive partial match) |
| `email` | string | No | Filter by email (case-insensitive partial match) |
| `vendor_id` | integer | No | Filter by vendor ID |
| `is_active` | boolean | No | Filter by active status |

#### Example Request (Admin)
```
GET /api/v1/vendor-users/?tenant_id=SAM001&skip=0&limit=10&is_active=true
```

#### Example Request (Employee)
```
GET /api/v1/vendor-users/?skip=0&limit=10&vendor_id=1
```

#### Success Response (200 OK)
```json
{
  "success": true,
  "message": "Retrieved 2 vendor user(s)",
  "data": {
    "total": 2,
    "items": [
      {
        "vendor_user_id": 1,
        "tenant_id": "SAM001",
        "name": "John Doe",
        "email": "john.doe@example.com",
        "phone": "+1234567890",
        "vendor_id": 1,
        "role_id": 5,
        "is_active": true,
        "created_at": "2025-11-26T12:00:00",
        "updated_at": "2025-11-26T12:00:00"
      },
      {
        "vendor_user_id": 2,
        "tenant_id": "SAM001",
        "name": "Jane Smith",
        "email": "jane.smith@example.com",
        "phone": "+1987654321",
        "vendor_id": 1,
        "role_id": 5,
        "is_active": true,
        "created_at": "2025-11-26T13:00:00",
        "updated_at": "2025-11-26T13:00:00"
      }
    ]
  },
  "error_code": null,
  "details": null,
  "timestamp": "2025-11-26 14:00:00"
}
```

---

### 3. Get Single Vendor User
**GET** `/api/v1/vendor-users/{vendor_user_id}`

Retrieves details of a specific vendor user.

#### Path Parameters
- `vendor_user_id` (integer): The vendor user ID

#### Query Parameters
- `tenant_id` (string): Required for Admin, automatic for Employee

#### Example Request (Admin)
```
GET /api/v1/vendor-users/1?tenant_id=SAM001
```

#### Example Request (Employee)
```
GET /api/v1/vendor-users/1
```

#### Success Response (200 OK)
```json
{
  "success": true,
  "message": "Vendor user retrieved successfully",
  "data": {
    "vendor_user_id": 1,
    "tenant_id": "SAM001",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "phone": "+1234567890",
    "vendor_id": 1,
    "role_id": 5,
    "is_active": true,
    "created_at": "2025-11-26T12:00:00",
    "updated_at": "2025-11-26T12:00:00"
  },
  "error_code": null,
  "details": null,
  "timestamp": "2025-11-26 14:00:00"
}
```

#### Error Response (404 Not Found)
```json
{
  "detail": {
    "success": false,
    "message": "Vendor user with ID 1 not found",
    "error_code": "VENDOR_USER_NOT_FOUND"
  }
}
```

---

### 4. Update Vendor User
**PUT** `/api/v1/vendor-users/{vendor_user_id}`

Updates an existing vendor user. Only provided fields will be updated.

#### Path Parameters
- `vendor_user_id` (integer): The vendor user ID

#### Query Parameters
- `tenant_id` (string): Required for Admin, automatic for Employee

#### Request Body (All fields optional)
```json
{
  "name": "John Updated",
  "email": "john.updated@example.com",
  "phone": "+1234567899",
  "password": "NewPassword123!",
  "vendor_id": 2,
  "role_id": 6,
  "is_active": false
}
```

#### Example Request (Admin)
```
PUT /api/v1/vendor-users/1?tenant_id=SAM001
Content-Type: application/json

{
  "name": "John Updated",
  "is_active": false
}
```

#### Success Response (200 OK)
```json
{
  "success": true,
  "message": "Vendor user updated successfully",
  "data": {
    "vendor_user_id": 1,
    "tenant_id": "SAM001",
    "name": "John Updated",
    "email": "john.doe@example.com",
    "phone": "+1234567890",
    "vendor_id": 1,
    "role_id": 5,
    "is_active": false,
    "created_at": "2025-11-26T12:00:00",
    "updated_at": "2025-11-26T15:00:00"
  },
  "error_code": null,
  "details": null,
  "timestamp": "2025-11-26 15:00:00"
}
```

#### Error Responses

**404 - Vendor User Not Found**
```json
{
  "detail": {
    "success": false,
    "message": "Vendor user with ID 1 not found",
    "error_code": "VENDOR_USER_NOT_FOUND"
  }
}
```

**400 - Duplicate Email**
```json
{
  "detail": {
    "success": false,
    "message": "Email 'john.updated@example.com' already exists in this tenant",
    "error_code": "DUPLICATE_EMAIL"
  }
}
```

---

### 5. Toggle Vendor User Status
**PATCH** `/api/v1/vendor-users/{vendor_user_id}/toggle-status`

Toggles the active status of a vendor user (active ↔ inactive).

#### Path Parameters
- `vendor_user_id` (integer): The vendor user ID

#### Query Parameters
- `tenant_id` (string): Required for Admin, automatic for Employee

#### Example Request (Admin)
```
PATCH /api/v1/vendor-users/1/toggle-status?tenant_id=SAM001
```

#### Example Request (Employee)
```
PATCH /api/v1/vendor-users/1/toggle-status
```

#### Success Response (200 OK)
```json
{
  "success": true,
  "message": "Vendor user is now inactive",
  "data": {
    "vendor_user_id": 1,
    "tenant_id": "SAM001",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "phone": "+1234567890",
    "vendor_id": 1,
    "role_id": 5,
    "is_active": false,
    "created_at": "2025-11-26T12:00:00",
    "updated_at": "2025-11-26T16:00:00"
  },
  "error_code": null,
  "details": null,
  "timestamp": "2025-11-26 16:00:00"
}
```

---

## Frontend Implementation Examples

### React/TypeScript Example

```typescript
// types.ts
export interface VendorUser {
  vendor_user_id: number;
  tenant_id: string;
  name: string;
  email: string;
  phone: string;
  vendor_id: number;
  role_id?: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface VendorUserCreate {
  name: string;
  email: string;
  phone: string;
  vendor_id: number;
  tenant_id?: string;  // Required for Admin
  role_id?: number;
  password: string;
  is_active: boolean;
}

export interface VendorUserUpdate {
  name?: string;
  email?: string;
  phone?: string;
  password?: string;
  vendor_id?: number;
  role_id?: number;
  is_active?: boolean;
}

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
  error_code: string | null;
  details: any | null;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  total: number;
  items: T[];
}

// api.ts
import axios from 'axios';

const API_BASE_URL = '/api/v1';

// Create Vendor User
export const createVendorUser = async (
  data: VendorUserCreate,
  token: string
): Promise<ApiResponse<VendorUser>> => {
  const response = await axios.post(
    `${API_BASE_URL}/vendor-users/`,
    data,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  return response.data;
};

// Get All Vendor Users
export const getVendorUsers = async (
  token: string,
  params: {
    tenant_id?: string;  // Required for Admin
    skip?: number;
    limit?: number;
    name?: string;
    email?: string;
    vendor_id?: number;
    is_active?: boolean;
  }
): Promise<ApiResponse<PaginatedResponse<VendorUser>>> => {
  const response = await axios.get(
    `${API_BASE_URL}/vendor-users/`,
    {
      headers: { 'Authorization': `Bearer ${token}` },
      params
    }
  );
  return response.data;
};

// Get Single Vendor User
export const getVendorUser = async (
  vendorUserId: number,
  token: string,
  tenantId?: string  // Required for Admin
): Promise<ApiResponse<VendorUser>> => {
  const response = await axios.get(
    `${API_BASE_URL}/vendor-users/${vendorUserId}`,
    {
      headers: { 'Authorization': `Bearer ${token}` },
      params: tenantId ? { tenant_id: tenantId } : {}
    }
  );
  return response.data;
};

// Update Vendor User
export const updateVendorUser = async (
  vendorUserId: number,
  data: VendorUserUpdate,
  token: string,
  tenantId?: string  // Required for Admin
): Promise<ApiResponse<VendorUser>> => {
  const response = await axios.put(
    `${API_BASE_URL}/vendor-users/${vendorUserId}`,
    data,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      params: tenantId ? { tenant_id: tenantId } : {}
    }
  );
  return response.data;
};

// Toggle Vendor User Status
export const toggleVendorUserStatus = async (
  vendorUserId: number,
  token: string,
  tenantId?: string  // Required for Admin
): Promise<ApiResponse<VendorUser>> => {
  const response = await axios.patch(
    `${API_BASE_URL}/vendor-users/${vendorUserId}/toggle-status`,
    {},
    {
      headers: { 'Authorization': `Bearer ${token}` },
      params: tenantId ? { tenant_id: tenantId } : {}
    }
  );
  return response.data;
};

// Component Example
import React, { useState, useEffect } from 'react';

const VendorUserList: React.FC = () => {
  const [vendorUsers, setVendorUsers] = useState<VendorUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Assume userType and tenantId come from auth context
  const userType = 'admin'; // or 'employee'
  const tenantId = 'SAM001';
  const token = 'your_auth_token';

  useEffect(() => {
    loadVendorUsers();
  }, []);

  const loadVendorUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = userType === 'admin' 
        ? { tenant_id: tenantId, skip: 0, limit: 100 }
        : { skip: 0, limit: 100 };
      
      const response = await getVendorUsers(token, params);
      if (response.success) {
        setVendorUsers(response.data.items);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail?.message || 'Failed to load vendor users');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleStatus = async (vendorUserId: number) => {
    try {
      const response = await toggleVendorUserStatus(
        vendorUserId,
        token,
        userType === 'admin' ? tenantId : undefined
      );
      if (response.success) {
        // Update local state
        setVendorUsers(prev =>
          prev.map(user =>
            user.vendor_user_id === vendorUserId
              ? { ...user, is_active: response.data.is_active }
              : user
          )
        );
      }
    } catch (err: any) {
      alert(err.response?.data?.detail?.message || 'Failed to toggle status');
    }
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <h2>Vendor Users</h2>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Email</th>
            <th>Phone</th>
            <th>Vendor ID</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {vendorUsers.map(user => (
            <tr key={user.vendor_user_id}>
              <td>{user.vendor_user_id}</td>
              <td>{user.name}</td>
              <td>{user.email}</td>
              <td>{user.phone}</td>
              <td>{user.vendor_id}</td>
              <td>{user.is_active ? 'Active' : 'Inactive'}</td>
              <td>
                <button onClick={() => handleToggleStatus(user.vendor_user_id)}>
                  Toggle Status
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
```

---

## Error Handling Best Practices

```typescript
// Error Handler Utility
export const handleApiError = (error: any): string => {
  if (error.response?.data?.detail) {
    const detail = error.response.data.detail;
    return detail.message || 'An error occurred';
  }
  return error.message || 'Network error';
};

// Usage in component
try {
  await createVendorUser(data, token);
} catch (error) {
  const errorMessage = handleApiError(error);
  setError(errorMessage);
}
```

---

## Common Error Codes

| Error Code | Description | HTTP Status |
|------------|-------------|-------------|
| `TENANT_ID_REQUIRED` | Tenant ID missing for admin or employee | 400/403 |
| `VENDOR_NOT_FOUND` | Vendor does not exist | 404 |
| `VENDOR_USER_NOT_FOUND` | Vendor user does not exist | 404 |
| `DUPLICATE_EMAIL` | Email already exists in tenant | 400 |
| `DUPLICATE_PHONE` | Phone already exists in tenant | 400 |
| `VENDOR_TENANT_MISMATCH` | Vendor doesn't belong to tenant | 403 |
| `UNAUTHORIZED_USER_TYPE` | User type not allowed | 403 |

---

## Audit Logging

All CREATE, UPDATE, and TOGGLE operations are automatically logged in the audit system. Logged actions include:
- **CREATE**: New vendor user creation with all details
- **UPDATE**: Field changes (old and new values)
- **TOGGLE**: Status changes (active/inactive)

No additional action required from frontend for audit logging.
