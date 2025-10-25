import requests
import json
from datetime import datetime, timedelta

def create_bookings_script():
    """
    Script to create bookings for all employees under SAM001 tenant
    for weekdays starting from 27/10/2025, excluding weekends.
    All bookings will have shift_id = 1.
    """
    
    # API configuration
    BASE_URL = "http://localhost:8000"
    EMPLOYEES_ENDPOINT = f"{BASE_URL}/api/v1/employees/"
    BOOKINGS_ENDPOINT = f"{BASE_URL}/api/v1/bookings/"
    
    # Headers (update with actual authorization token)
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMSIsIm9wYXF1ZV90b2tlbiI6IjA3MTMxNTI4N2RiNmI3YThkNTE0NmUwODYyM2NmYjU3IiwidG9rZW5fdHlwZSI6ImFjY2VzcyIsInVzZXJfdHlwZSI6ImFkbWluIiwiZXhwIjoxNzYxNTA1NDc0LCJpYXQiOjE3NjE0MTkwNzR9.uAvtRfCoREQ69oydPf9B2hjNS9riWB9A9-R8rD5lQ3w"
    }
    
    # Office location (drop location for all bookings)
    OFFICE_LOCATION = {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "address": "MG Road, Bangalore, Karnataka, India"
    }
    
    # Date configuration - start from 27/10/2025
    start_date = datetime(2025, 10, 27)  # Monday
    num_weekdays = 5  # Create bookings for 1 week (Mon-Fri)
    
    created_bookings = []
    failed_bookings = []
    
    try:
        # Step 1: Fetch all employees under SAM001 tenant
        print("📋 Fetching employees under SAM001 tenant...")
        
        # Use query parameters for employee API call
        employees_response = requests.get(
            f"{EMPLOYEES_ENDPOINT}?skip=0&limit=100&tenant_id=SAM001", 
            headers=headers
        )
        

        if employees_response.status_code != 200:
            print(f"❌ Failed to fetch employees: {employees_response.status_code}")
            if employees_response.content:
                error_detail = employees_response.json()
                print(f"Error details: {error_detail}")
            return
        
        employees_data = employees_response.json()
        employees = employees_data.get("data", {}).get("items", [])
        
        if not employees:
            print("❌ No employees found under SAM001 tenant")
            print(f"Response data: {employees_data}")
            return
        
        print(f"✅ Found {len(employees)} employees under SAM001 tenant")
        
        # Step 2: Generate weekdays starting from 27/10/2025
        weekdays = []
        current_date = start_date
        
        while len(weekdays) < num_weekdays:
            # Check if it's a weekday (Monday=0, Sunday=6)
            if current_date.weekday() < 5:  # 0-4 are Monday to Friday
                weekdays.append(current_date.date())
            current_date += timedelta(days=1)
        
        print(f"📅 Creating bookings for dates: {[str(date) for date in weekdays]}")
        
        # Step 3: Create bookings for each employee for each weekday
        total_bookings = len(employees) * len(weekdays)
        booking_count = 0
        
        for employee in employees:
            employee_id = employee.get("employee_id")
            employee_name = employee.get("name")
            employee_code = employee.get("employee_code")
            team_id = employee.get("team_id")
            
            print(f"\n--- Creating bookings for {employee_name} (ID: {employee_id}) ---")
            
            # Create booking data with booking_dates array for all weekdays at once
            booking_data = {
                "tenant_id": "SAM001",
                "employee_id": employee_id,
                "booking_dates": [str(date) for date in weekdays],
                "shift_id": 1
            }
            
            try:
                response = requests.post(BOOKINGS_ENDPOINT, headers=headers, json=booking_data)
                
                if response.status_code == 201:
                    result = response.json()
                    # Handle response for multiple bookings
                    booking_data_response = result.get("data", {})
                    
                    for booking_date in weekdays:
                        created_bookings.append({
                            "booking_id": f"Generated for {employee_id}",
                            "employee_name": employee_name,
                            "employee_id": employee_id,
                            "booking_date": str(booking_date),
                            "shift_id": 1
                        })
                    
                    print(f"✅ Created {len(weekdays)} bookings for {employee_name}")
                else:
                    error_detail = response.json() if response.content else "Unknown error"
                    for booking_date in weekdays:
                        failed_bookings.append({
                            "employee_name": employee_name,
                            "employee_id": employee_id,
                            "booking_date": str(booking_date),
                            "error": error_detail,
                            "status_code": response.status_code
                        })
                    print(f"❌ Failed bookings for {employee_name}: {response.status_code} - {error_detail}")
                    
            except requests.exceptions.RequestException as e:
                for booking_date in weekdays:
                    failed_bookings.append({
                        "employee_name": employee_name,
                        "employee_id": employee_id,
                        "booking_date": str(booking_date),
                        "error": str(e),
                        "status_code": "Network Error"
                    })
                print(f"❌ Network error for {employee_name}: {str(e)}")
    
    except Exception as e:
        print(f"❌ Script error: {str(e)}")
        return
    
    # Summary
    print(f"\n{'='*60}")
    print(f"BOOKING CREATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total Employees: {len(employees)}")
    print(f"Weekdays: {len(weekdays)} ({weekdays[0]} to {weekdays[-1]})")
    print(f"Total Bookings Attempted: {total_bookings}")
    print(f"Successfully Created: {len(created_bookings)}")
    print(f"Failed: {len(failed_bookings)}")
    
    if created_bookings:
        print(f"\n✅ Successfully Created Bookings: {len(created_bookings)}")
        # Group by employee
        employees_summary = {}
        for booking in created_bookings:
            emp_name = booking["employee_name"]
            if emp_name not in employees_summary:
                employees_summary[emp_name] = 0
            employees_summary[emp_name] += 1
        
        for emp_name, count in employees_summary.items():
            print(f"   - {emp_name}: {count} bookings")
    
    if failed_bookings:
        print(f"\n❌ Failed Bookings: {len(failed_bookings)}")
        for booking in failed_bookings[:10]:  # Show first 10 failures
            print(f"   - {booking['employee_name']} ({booking['booking_date']}): {booking['error']}")
        if len(failed_bookings) > 10:
            print(f"   ... and {len(failed_bookings) - 10} more")
    
    # Save results to file
    results = {
        "summary": {
            "total_employees": len(employees),
            "weekdays_count": len(weekdays),
            "weekdays": [str(date) for date in weekdays],
            "total_attempted": total_bookings,
            "successful": len(created_bookings),
            "failed": len(failed_bookings)
        },
        "created_bookings": created_bookings,
        "failed_bookings": failed_bookings
    }
    
    filename = f'booking_creation_results_{start_date.strftime("%Y%m%d")}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to '{filename}'")
    
    return results

if __name__ == "__main__":
    # Configuration reminder
    print("🔧 BOOKING CREATION CONFIGURATION:")
    print("1. Update BASE_URL with your actual API endpoint")
    print("2. Replace authorization token with a valid one")
    print("3. Ensure SAM001 tenant exists and has employees")
    print("4. Ensure shift_id = 1 exists in your database")
    print("5. Make sure you have proper permissions (booking.create)")
    print("\nBooking Details:")
    print("- Tenant: SAM001")
    print("- Start Date: 27/10/2025 (Monday)")
    print("- Schedule: Weekdays only (Mon-Fri)")
    print("- Shift ID: 1 for all bookings")
    print("- Pickup: Employee's home location")
    print("- Drop: Office location (MG Road, Bangalore)")
    print("\nPress Enter to continue or Ctrl+C to exit...")
    input()
    
    # Run the script
    results = create_bookings_script()
