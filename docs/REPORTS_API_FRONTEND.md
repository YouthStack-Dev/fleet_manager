# Reports API - Frontend Integration Guide

## Base URL
```
http://localhost:8000/api/reports
```

---

## 1. Export Bookings Report (Excel Download)

### Endpoint
```
GET /api/reports/bookings/export
```

### Description
Downloads a comprehensive Excel report with detailed booking, route, employee, driver, vehicle, and vendor information.

### Authentication
Required: Bearer Token in Authorization header

### Query Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `start_date` | string (date) | **Yes** | Start date (YYYY-MM-DD) | `2025-11-19` |
| `end_date` | string (date) | **Yes** | End date (YYYY-MM-DD) | `2025-11-30` |
| `tenant_id` | string | **Admin only** | Tenant ID filter | `SAM001` |
| `shift_id` | integer | No | Filter by shift | `1` |
| `booking_status` | array[string] | No | Filter by booking status | `["Request", "Scheduled"]` |
| `route_status` | array[string] | No | Filter by route status | `["Completed"]` |
| `vendor_id` | integer | No | Filter by vendor | `5` |
| `include_unrouted` | boolean | No | Include unrouted bookings (default: true) | `true` |

### Booking Status Options
- `Request` - Initial booking state
- `Scheduled` - Assigned to route
- `Ongoing` - Trip in progress
- `Completed` - Trip completed
- `Cancelled` - Booking cancelled
- `No-Show` - Employee didn't show up
- `Expired` - Auto-cancelled

### Route Status Options
- `Planned` - Route created but not assigned
- `Vendor Assigned` - Assigned to vendor
- `Driver Assigned` - Driver assigned
- `Ongoing` - Trip in progress
- `Completed` - Trip completed
- `Cancelled` - Route cancelled

### Validations
- ✅ Date range cannot exceed 90 days
- ✅ `start_date` must be before or equal to `end_date`
- ✅ Admin users must provide `tenant_id`
- ✅ Employee users automatically scoped to their tenant
- ✅ Vendor users automatically scoped to their tenant and vendor

### Response
- **Content-Type**: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- **File Name**: `bookings_report_{tenant_id}_{start_date}_to_{end_date}.xlsx`
- **File Size**: Varies (typically 50KB - 5MB)

### Frontend Implementation Examples

#### JavaScript/React - Axios
```javascript
import axios from 'axios';

const downloadBookingsReport = async () => {
  try {
    const params = {
      start_date: '2025-11-19',
      end_date: '2025-11-30',
      tenant_id: 'SAM001',
      shift_id: 1,
      booking_status: ['Request', 'Scheduled'],
      include_unrouted: true
    };

    const response = await axios.get(
      'http://localhost:8000/api/reports/bookings/export',
      {
        params: params,
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        responseType: 'blob' // Important for file download
      }
    );

    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `bookings_report_${params.start_date}_to_${params.end_date}.xlsx`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);

    console.log('Report downloaded successfully');
  } catch (error) {
    console.error('Error downloading report:', error.response?.data || error.message);
  }
};
```

#### JavaScript/React - Fetch API
```javascript
const downloadBookingsReport = async () => {
  try {
    const params = new URLSearchParams({
      start_date: '2025-11-19',
      end_date: '2025-11-30',
      tenant_id: 'SAM001',
      shift_id: '1',
      include_unrouted: 'true'
    });

    // Add multiple booking_status values
    params.append('booking_status', 'Request');
    params.append('booking_status', 'Scheduled');

    const response = await fetch(
      `http://localhost:8000/api/reports/bookings/export?${params}`,
      {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'bookings_report.xlsx';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    console.log('Report downloaded successfully');
  } catch (error) {
    console.error('Download error:', error);
  }
};
```

#### React Component Example
```jsx
import React, { useState } from 'react';
import axios from 'axios';

const ReportDownloader = () => {
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    start_date: '2025-11-19',
    end_date: '2025-11-30',
    tenant_id: 'SAM001',
    shift_id: '',
    booking_status: [],
    include_unrouted: true
  });

  const handleDownload = async () => {
    setLoading(true);
    try {
      const response = await axios.get(
        'http://localhost:8000/api/reports/bookings/export',
        {
          params: filters,
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          },
          responseType: 'blob'
        }
      );

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `bookings_report_${filters.start_date}_to_${filters.end_date}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      alert('Report downloaded successfully!');
    } catch (error) {
      console.error('Error:', error);
      alert('Failed to download report');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2>Download Bookings Report</h2>
      
      <input
        type="date"
        value={filters.start_date}
        onChange={(e) => setFilters({...filters, start_date: e.target.value})}
      />
      
      <input
        type="date"
        value={filters.end_date}
        onChange={(e) => setFilters({...filters, end_date: e.target.value})}
      />
      
      <button onClick={handleDownload} disabled={loading}>
        {loading ? 'Downloading...' : 'Download Excel Report'}
      </button>
    </div>
  );
};

export default ReportDownloader;
```

---

## 2. Get Bookings Analytics (JSON)

### Endpoint
```
GET /api/reports/bookings/analytics
```

### Description
Returns statistical analytics and summary data for bookings in JSON format.

### Authentication
Required: Bearer Token in Authorization header

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string (date) | **Yes** | Start date (YYYY-MM-DD) |
| `end_date` | string (date) | **Yes** | End date (YYYY-MM-DD) |
| `tenant_id` | string | **Admin only** | Tenant ID |
| `shift_id` | integer | No | Filter by shift |

### Response Structure

```json
{
  "success": true,
  "message": "Analytics generated successfully",
  "data": {
    "date_range": {
      "start_date": "2025-11-19",
      "end_date": "2025-11-30"
    },
    "total_bookings": 250,
    "total_shifts": 3,
    "booking_status_breakdown": {
      "Request": 20,
      "Scheduled": 50,
      "Ongoing": 10,
      "Completed": 150,
      "Cancelled": 15,
      "No-Show": 5
    },
    "routing_summary": {
      "routed": 230,
      "unrouted": 20,
      "routing_percentage": 92.0
    },
    "assignment_summary": {
      "vendor_assigned": 180,
      "driver_assigned": 160,
      "vendor_assignment_percentage": 72.0,
      "driver_assignment_percentage": 64.0
    },
    "route_status_breakdown": {
      "Planned": 10,
      "Vendor Assigned": 20,
      "Driver Assigned": 30,
      "Ongoing": 10,
      "Completed": 150,
      "Cancelled": 10
    },
    "completion_rate": 60.0,
    "daily_breakdown": {
      "2025-11-19": {
        "booking_status": {
          "Request": 53,
          "Scheduled": 13,
          "Ongoing": 5,
          "Completed": 10
        },
        "vendor_assigned": 28,
        "driver_assigned": 18
      },
      "2025-11-20": {
        "booking_status": {
          "Request": 66,
          "Scheduled": 20,
          "Completed": 15
        },
        "vendor_assigned": 35,
        "driver_assigned": 25
      }
    }
  }
}
```

### Response Fields Explanation

#### Top Level
- `total_bookings` - Total number of bookings in date range
- `total_shifts` - Number of unique shifts involved
- `booking_status_breakdown` - Count of bookings by status
- `routing_summary` - Routing statistics
- `assignment_summary` - Vendor and driver assignment stats
- `route_status_breakdown` - Count of routes by status
- `completion_rate` - Percentage of completed bookings
- `daily_breakdown` - Day-by-day breakdown

#### Daily Breakdown Structure
Each date contains:
- `booking_status` - Object with status counts for that day
- `vendor_assigned` - Number of bookings with vendor assigned
- `driver_assigned` - Number of bookings with driver assigned

### Frontend Implementation Examples

#### JavaScript/React - Axios
```javascript
import axios from 'axios';

const fetchAnalytics = async () => {
  try {
    const params = {
      start_date: '2025-11-19',
      end_date: '2025-11-30',
      tenant_id: 'SAM001',
      shift_id: 1
    };

    const response = await axios.get(
      'http://localhost:8000/api/reports/bookings/analytics',
      {
        params: params,
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      }
    );

    if (response.data.success) {
      const analytics = response.data.data;
      console.log('Analytics:', analytics);
      
      // Use the data
      console.log('Total Bookings:', analytics.total_bookings);
      console.log('Completion Rate:', analytics.completion_rate + '%');
      console.log('Vendor Assigned:', analytics.assignment_summary.vendor_assigned);
      
      return analytics;
    }
  } catch (error) {
    console.error('Error fetching analytics:', error.response?.data || error.message);
  }
};
```

#### React Component with Chart Integration
```jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Pie } from 'react-chartjs-2';

ChartJS.register(ArcElement, Tooltip, Legend);

const AnalyticsDashboard = () => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    try {
      const response = await axios.get(
        'http://localhost:8000/api/reports/bookings/analytics',
        {
          params: {
            start_date: '2025-11-19',
            end_date: '2025-11-30',
            tenant_id: 'SAM001'
          },
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (response.data.success) {
        setAnalytics(response.data.data);
      }
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (!analytics) return <div>No data available</div>;

  // Prepare chart data
  const chartData = {
    labels: Object.keys(analytics.booking_status_breakdown),
    datasets: [{
      label: 'Bookings by Status',
      data: Object.values(analytics.booking_status_breakdown),
      backgroundColor: [
        '#FF6384',
        '#36A2EB',
        '#FFCE56',
        '#4BC0C0',
        '#9966FF',
        '#FF9F40'
      ]
    }]
  };

  return (
    <div>
      <h2>Bookings Analytics Dashboard</h2>
      
      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Bookings</h3>
          <p>{analytics.total_bookings}</p>
        </div>
        
        <div className="stat-card">
          <h3>Total Shifts</h3>
          <p>{analytics.total_shifts}</p>
        </div>
        
        <div className="stat-card">
          <h3>Completion Rate</h3>
          <p>{analytics.completion_rate}%</p>
        </div>
        
        <div className="stat-card">
          <h3>Routing Percentage</h3>
          <p>{analytics.routing_summary.routing_percentage.toFixed(2)}%</p>
        </div>
      </div>

      <div className="charts-section">
        <div className="chart-container">
          <h3>Booking Status Distribution</h3>
          <Pie data={chartData} />
        </div>
      </div>

      <div className="assignment-summary">
        <h3>Assignment Summary</h3>
        <p>Vendor Assigned: {analytics.assignment_summary.vendor_assigned} ({analytics.assignment_summary.vendor_assignment_percentage.toFixed(2)}%)</p>
        <p>Driver Assigned: {analytics.assignment_summary.driver_assigned} ({analytics.assignment_summary.driver_assignment_percentage.toFixed(2)}%)</p>
      </div>

      <div className="daily-breakdown">
        <h3>Daily Breakdown</h3>
        {Object.entries(analytics.daily_breakdown).map(([date, data]) => (
          <div key={date} className="daily-item">
            <h4>{date}</h4>
            <p>Statuses: {JSON.stringify(data.booking_status)}</p>
            <p>Vendor Assigned: {data.vendor_assigned}</p>
            <p>Driver Assigned: {data.driver_assigned}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AnalyticsDashboard;
```

---

## Error Handling

### Common Error Responses

#### 400 Bad Request
```json
{
  "success": false,
  "message": "start_date cannot be after end_date",
  "error_code": "INVALID_DATE_RANGE"
}
```

#### 403 Forbidden
```json
{
  "success": false,
  "message": "Insufficient permissions to generate reports",
  "error_code": "FORBIDDEN"
}
```

#### 404 Not Found
```json
{
  "success": false,
  "message": "No bookings found matching the specified filters",
  "error_code": "NO_DATA_FOUND"
}
```

### Frontend Error Handling Example
```javascript
try {
  const response = await axios.get(url, config);
  // Success handling
} catch (error) {
  if (error.response) {
    // Server responded with error
    const { status, data } = error.response;
    
    switch (status) {
      case 400:
        alert(`Invalid request: ${data.message}`);
        break;
      case 403:
        alert('You do not have permission to access this report');
        break;
      case 404:
        alert('No data found for the selected filters');
        break;
      default:
        alert('An error occurred. Please try again.');
    }
  } else if (error.request) {
    // Request made but no response
    alert('Server not responding. Please check your connection.');
  } else {
    // Other errors
    alert('An unexpected error occurred.');
  }
}
```

---

## Best Practices

### 1. Date Range Selection
```javascript
// Validate date range before making request
const validateDateRange = (startDate, endDate) => {
  const start = new Date(startDate);
  const end = new Date(endDate);
  const diffDays = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
  
  if (diffDays < 0) {
    throw new Error('End date must be after start date');
  }
  
  if (diffDays > 90) {
    throw new Error('Date range cannot exceed 90 days');
  }
  
  return true;
};
```

### 2. Loading States
```jsx
const [isDownloading, setIsDownloading] = useState(false);

const handleDownload = async () => {
  setIsDownloading(true);
  try {
    // Download logic
  } finally {
    setIsDownloading(false);
  }
};

return (
  <button onClick={handleDownload} disabled={isDownloading}>
    {isDownloading ? 'Downloading...' : 'Download Report'}
  </button>
);
```

### 3. Progress Indication for Large Reports
```javascript
const downloadWithProgress = async () => {
  const response = await axios.get(url, {
    responseType: 'blob',
    onDownloadProgress: (progressEvent) => {
      const percentCompleted = Math.round(
        (progressEvent.loaded * 100) / progressEvent.total
      );
      setProgress(percentCompleted);
    }
  });
};
```

### 4. Caching Analytics Data
```javascript
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

const getCachedAnalytics = (key) => {
  const cached = localStorage.getItem(key);
  if (!cached) return null;
  
  const { data, timestamp } = JSON.parse(cached);
  const isExpired = Date.now() - timestamp > CACHE_DURATION;
  
  return isExpired ? null : data;
};

const setCachedAnalytics = (key, data) => {
  localStorage.setItem(key, JSON.stringify({
    data,
    timestamp: Date.now()
  }));
};
```

---

## Testing

### Postman/Insomnia

#### Excel Download Test
1. Method: GET
2. URL: `http://localhost:8000/api/reports/bookings/export?start_date=2025-11-19&end_date=2025-11-30&tenant_id=SAM001`
3. Headers: `Authorization: Bearer YOUR_TOKEN`
4. Click **"Send and Download"**
5. Save as `.xlsx` file

#### Analytics Test
1. Method: GET
2. URL: `http://localhost:8000/api/reports/bookings/analytics?start_date=2025-11-19&end_date=2025-11-30&tenant_id=SAM001`
3. Headers: `Authorization: Bearer YOUR_TOKEN`
4. Response will be JSON

### cURL Examples

#### Excel Download
```bash
curl -X GET \
  "http://localhost:8000/api/reports/bookings/export?start_date=2025-11-19&end_date=2025-11-30&tenant_id=SAM001&shift_id=1&booking_status=Request&include_unrouted=true" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  --output report.xlsx
```

#### Analytics
```bash
curl -X GET \
  "http://localhost:8000/api/reports/bookings/analytics?start_date=2025-11-19&end_date=2025-11-30&tenant_id=SAM001" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Notes for Frontend Developers

1. **File Download**: Always use `responseType: 'blob'` for Excel downloads
2. **Multiple Values**: Use `params.append()` or array syntax for multiple booking_status values
3. **Date Format**: Use ISO format (YYYY-MM-DD) for all dates
4. **Authorization**: Include Bearer token in all requests
5. **Error Handling**: Always handle 400, 403, and 404 errors
6. **Large Reports**: May take 10-30 seconds for reports with 1000+ bookings
7. **Caching**: Consider caching analytics data for 5 minutes to reduce API calls
8. **User Feedback**: Show loading spinners and progress indicators
9. **Date Validation**: Validate date ranges client-side before API call
10. **File Naming**: Use descriptive filenames with date range for downloaded reports

---

## Support

For issues or questions, contact the backend team or refer to the main API documentation at `/docs/REPORTS_API.md`

**Version**: 1.0  
**Last Updated**: November 19, 2025
