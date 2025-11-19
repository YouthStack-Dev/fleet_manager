# Reports API Documentation

## Overview

The Reports API provides comprehensive analytics and Excel export functionality for bookings, routes, and assignments. It allows users to generate detailed reports with various filters and download them as Excel files.

## Endpoints

### 1. Export Bookings Report (Excel)

**Endpoint:** `GET /api/reports/bookings/export`

**Description:** Generate and download a comprehensive Excel report with detailed booking, route, employee, driver, vehicle, and vendor information.

**Authentication:** Required (Bearer Token with `report.read` permission)

**Query Parameters:**

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `start_date` | date | Yes | Start date for report (YYYY-MM-DD) | `2025-01-01` |
| `end_date` | date | Yes | End date for report (YYYY-MM-DD) | `2025-01-31` |
| `tenant_id` | string | Admin only | Tenant ID to filter | `tenant_001` |
| `shift_id` | integer | No | Filter by specific shift | `1` |
| `booking_status` | array[enum] | No | Filter by booking status (can select multiple) | `COMPLETED`, `SCHEDULED` |
| `route_status` | array[enum] | No | Filter by route status (can select multiple) | `COMPLETED`, `ONGOING` |
| `vendor_id` | integer | No | Filter by vendor | `5` |
| `include_unrouted` | boolean | No | Include bookings without routes (default: true) | `true` |

**Booking Status Options:**
- `REQUEST`
- `SCHEDULED`
- `ONGOING`
- `COMPLETED`
- `CANCELLED`
- `NO_SHOW`
- `EXPIRED`

**Route Status Options:**
- `PLANNED`
- `VENDOR_ASSIGNED`
- `DRIVER_ASSIGNED`
- `ONGOING`
- `COMPLETED`
- `CANCELLED`

**Validations:**
- Date range is required
- Date range cannot exceed 90 days
- `start_date` cannot be after `end_date`
- Admin users must provide `tenant_id`
- Employee users are automatically restricted to their tenant
- Vendor users are automatically restricted to their tenant and vendor

**Response:**
- **Success (200):** Excel file download with two sheets:
  1. **Bookings Report** - Detailed booking data
  2. **Summary** - Statistics and metadata

**Excel Report Columns:**

| Column | Description |
|--------|-------------|
| Booking ID | Unique booking identifier |
| Booking Date | Date of the booking |
| Booking Status | Current booking status |
| Employee ID | Employee's unique ID |
| Employee Code | Employee's code/number |
| Employee Name | Full name of employee |
| Employee Phone | Employee contact number |
| Employee Gender | Employee gender |
| Shift ID | Shift identifier |
| Shift Code | Shift code/identifier |
| Shift Time | Shift start time |
| Shift Type | IN or OUT |
| Pickup Location | Pickup address |
| Pickup Latitude | Pickup coordinates (lat) |
| Pickup Longitude | Pickup coordinates (lon) |
| Drop Location | Drop address |
| Drop Latitude | Drop coordinates (lat) |
| Drop Longitude | Drop coordinates (lon) |
| Route ID | Associated route ID |
| Route Code | Route code/name |
| Route Status | Current route status |
| Stop Order | Order in route sequence |
| Estimated Pickup Time | Planned pickup time |
| Estimated Drop Time | Planned drop time |
| Actual Pickup Time | Actual pickup time |
| Actual Drop Time | Actual drop time |
| Distance (km) | Distance for this stop |
| Driver ID | Assigned driver ID |
| Driver Name | Driver's name |
| Driver Phone | Driver contact |
| Driver License | License number |
| Vehicle ID | Assigned vehicle ID |
| Vehicle Number | Vehicle registration number |
| Vendor ID | Assigned vendor ID |
| Vendor Name | Vendor company name |
| Vendor Phone | Vendor contact |
| Reason | Booking notes/reason |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/reports/bookings/export?start_date=2025-01-01&end_date=2025-01-31&shift_id=1&booking_status=COMPLETED&booking_status=NO_SHOW&include_unrouted=false" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o bookings_report.xlsx
```

**Example Request (Multiple Filters):**

```bash
GET /api/reports/bookings/export?start_date=2025-11-01&end_date=2025-11-19&tenant_id=tenant_123&shift_id=2&booking_status=COMPLETED&booking_status=SCHEDULED&route_status=COMPLETED&vendor_id=3&include_unrouted=false
```

**Error Responses:**

- **400 Bad Request:**
  ```json
  {
    "success": false,
    "message": "start_date cannot be after end_date",
    "error_code": "INVALID_DATE_RANGE"
  }
  ```

- **403 Forbidden:**
  ```json
  {
    "success": false,
    "message": "Insufficient permissions to generate reports",
    "error_code": "FORBIDDEN"
  }
  ```

- **404 Not Found:**
  ```json
  {
    "success": false,
    "message": "No bookings found matching the specified filters",
    "error_code": "NO_DATA_FOUND"
  }
  ```

---

### 2. Get Bookings Analytics (JSON)

**Endpoint:** `GET /api/reports/bookings/analytics`

**Description:** Get statistical analytics and summary data for bookings within a date range (JSON format).

**Authentication:** Required (Bearer Token with `report.read` permission)

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | date | Yes | Start date (YYYY-MM-DD) |
| `end_date` | date | Yes | End date (YYYY-MM-DD) |
| `tenant_id` | string | Admin only | Tenant ID to filter |
| `shift_id` | integer | No | Filter by shift |

**Response Structure:**

```json
{
  "success": true,
  "message": "Analytics generated successfully",
  "data": {
    "date_range": {
      "start_date": "2025-11-01",
      "end_date": "2025-11-19"
    },
    "total_bookings": 250,
    "booking_status_breakdown": {
      "REQUEST": 20,
      "SCHEDULED": 50,
      "ONGOING": 10,
      "COMPLETED": 150,
      "CANCELLED": 15,
      "NO_SHOW": 5
    },
    "routing_summary": {
      "routed": 230,
      "unrouted": 20,
      "routing_percentage": 92.0
    },
    "route_status_breakdown": {
      "PLANNED": 10,
      "VENDOR_ASSIGNED": 20,
      "DRIVER_ASSIGNED": 30,
      "ONGOING": 10,
      "COMPLETED": 150,
      "CANCELLED": 10
    },
    "completion_rate": 60.0,
    "daily_breakdown": {
      "2025-11-01": {
        "COMPLETED": 10,
        "SCHEDULED": 5,
        "REQUEST": 2
      },
      "2025-11-02": {
        "COMPLETED": 12,
        "NO_SHOW": 1
      }
      // ... more dates
    }
  }
}
```

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/reports/bookings/analytics?start_date=2025-11-01&end_date=2025-11-19&tenant_id=tenant_123&shift_id=1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## User Type Access Control

### Admin Users
- Can access reports for any tenant by specifying `tenant_id`
- Must provide `tenant_id` in request
- Can see all bookings, routes, vendors, etc. for the specified tenant

### Employee Users
- Automatically restricted to their own tenant
- Cannot specify different `tenant_id`
- Can see all data within their tenant

### Vendor Users
- Automatically restricted to their own tenant and vendor
- Can only see bookings/routes assigned to their vendor
- Cannot see other vendors' data

### Driver Users
- Not permitted to access reports (403 Forbidden)

---

## Common Use Cases

### 1. Daily Completed Bookings Report
```bash
GET /api/reports/bookings/export?start_date=2025-11-19&end_date=2025-11-19&booking_status=COMPLETED&tenant_id=tenant_123
```

### 2. Monthly No-Show Report
```bash
GET /api/reports/bookings/export?start_date=2025-11-01&end_date=2025-11-30&booking_status=NO_SHOW&tenant_id=tenant_123
```

### 3. Unrouted Bookings Report
```bash
GET /api/reports/bookings/export?start_date=2025-11-19&end_date=2025-11-19&booking_status=REQUEST&include_unrouted=true&tenant_id=tenant_123
```

### 4. Vendor Performance Report
```bash
GET /api/reports/bookings/export?start_date=2025-11-01&end_date=2025-11-19&vendor_id=5&route_status=COMPLETED&tenant_id=tenant_123
```

### 5. Shift-Specific Report
```bash
GET /api/reports/bookings/export?start_date=2025-11-01&end_date=2025-11-19&shift_id=2&tenant_id=tenant_123
```

### 6. Weekly Analytics Summary
```bash
GET /api/reports/bookings/analytics?start_date=2025-11-13&end_date=2025-11-19&tenant_id=tenant_123
```

---

## Error Handling

### Common Error Codes

| Error Code | Description | Solution |
|------------|-------------|----------|
| `INVALID_DATE_RANGE` | start_date is after end_date | Correct the date order |
| `DATE_RANGE_TOO_LARGE` | Date range exceeds 90 days | Reduce the date range |
| `TENANT_ID_REQUIRED` | Admin user didn't provide tenant_id | Add tenant_id parameter |
| `TENANT_NOT_FOUND` | Specified tenant doesn't exist | Verify tenant_id |
| `SHIFT_NOT_FOUND` | Shift doesn't belong to tenant | Verify shift_id |
| `NO_DATA_FOUND` | No bookings match filters | Adjust filter criteria |
| `FORBIDDEN` | Insufficient permissions | Check user permissions |

---

## Performance Considerations

1. **Date Range Limit:** Maximum 90 days to prevent performance issues
2. **Large Reports:** Reports with 1000+ bookings may take 10-30 seconds to generate
3. **Concurrent Requests:** Limit to 2-3 concurrent report generations per user
4. **Caching:** Consider caching analytics data for frequently requested date ranges

---

## Excel File Structure

### Sheet 1: Bookings Report
- Professional blue header styling
- Frozen header row for easy scrolling
- Auto-adjusted column widths
- All booking and route details

### Sheet 2: Summary
- Report metadata (generated date, user, tenant)
- Total bookings count
- Routed vs unrouted breakdown
- Status distribution table

---

## Integration Examples

### Python Example
```python
import requests

url = "http://localhost:8000/api/reports/bookings/export"
params = {
    "start_date": "2025-11-01",
    "end_date": "2025-11-19",
    "tenant_id": "tenant_123",
    "booking_status": ["COMPLETED", "NO_SHOW"]
}
headers = {"Authorization": f"Bearer {token}"}

response = requests.get(url, params=params, headers=headers)

if response.status_code == 200:
    with open("report.xlsx", "wb") as f:
        f.write(response.content)
    print("Report downloaded successfully")
```

### JavaScript Example
```javascript
const axios = require('axios');
const fs = require('fs');

const url = 'http://localhost:8000/api/reports/bookings/export';
const params = {
  start_date: '2025-11-01',
  end_date: '2025-11-19',
  tenant_id: 'tenant_123',
  booking_status: ['COMPLETED', 'NO_SHOW']
};
const headers = { Authorization: `Bearer ${token}` };

axios.get(url, { params, headers, responseType: 'arraybuffer' })
  .then(response => {
    fs.writeFileSync('report.xlsx', response.data);
    console.log('Report downloaded successfully');
  });
```

---

## Best Practices

1. **Always specify date ranges** - Don't rely on defaults
2. **Use specific filters** - Reduces report size and generation time
3. **Download during off-peak hours** - For large reports
4. **Validate dates** - Before making API calls
5. **Handle errors gracefully** - Show user-friendly messages
6. **Store reports temporarily** - Don't generate same report multiple times
7. **Use analytics endpoint first** - Check data availability before downloading Excel

---

## Changelog

### Version 1.0 (2025-11-19)
- Initial release
- Excel export with comprehensive booking details
- JSON analytics endpoint
- Support for multiple filters (date, shift, status, vendor)
- Role-based access control
- Summary sheet with statistics
