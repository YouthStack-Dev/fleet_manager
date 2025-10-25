import requests
import json
import random

def create_employees_script():
    """
    Script to create 30 employees using the /employees endpoint.
    Creates 10 groups of 3 employees each, with employees in each group located near each other in Bangalore.
    """
    
    # API configuration
    BASE_URL = "http://localhost:8000"  # Update with your actual API URL
    ENDPOINT = f"{BASE_URL}/api/v1/employees/"
    
    # Headers (update with actual authorization token)
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMSIsIm9wYXF1ZV90b2tlbiI6ImE1NTQxN2YxOTYzMDBhOGMyNTZmYzQ4NDc0ZGIyZmViIiwidG9rZW5fdHlwZSI6ImFjY2VzcyIsInVzZXJfdHlwZSI6ImFkbWluIiwiZXhwIjoxNzYxNDAxMTU1LCJpYXQiOjE3NjEzMTQ3NTV9.hH5nbZ1-dG8yxMYNOq_a09iLUoC49804hvLuLpRq4S4"  # Replace with actual token
    }
    
    # Bangalore areas with coordinates
    bangalore_areas = [
        {"area": "Koramangala", "lat": 12.9352, "lng": 77.6245},
        {"area": "Indiranagar", "lat": 12.9719, "lng": 77.6412},
        {"area": "Whitefield", "lat": 12.9698, "lng": 77.7500},
        {"area": "Electronic City", "lat": 12.8456, "lng": 77.6603},
        {"area": "Hebbal", "lat": 13.0358, "lng": 77.5970},
        {"area": "BTM Layout", "lat": 12.9165, "lng": 77.6101},
        {"area": "Jayanagar", "lat": 12.9254, "lng": 77.5837},
        {"area": "Rajajinagar", "lat": 12.9915, "lng": 77.5520},
        {"area": "Marathahalli", "lat": 12.9591, "lng": 77.6974},
        {"area": "Banashankari", "lat": 12.9081, "lng": 77.5737}
    ]
    
    # Employee names
    names = [
        "Rajesh Kumar", "Priya Sharma", "Amit Patel", "Sneha Singh", "Vikram Reddy",
        "Anitha Nair", "Suresh Gupta", "Kavya Rao", "Rohit Jain", "Deepika Iyer",
        "Manoj Kumar", "Shweta Agarwal", "Kiran Shetty", "Meera Krishnan", "Arun Verma",
        "Divya Menon", "Santosh Pillai", "Ritu Bansal", "Harish Bhat", "Pooja Desai",
        "Naveen Chandra", "Lakshmi Devi", "Ravi Teja", "Sunita Joshi", "Prakash Rao",
        "Nisha Kapoor", "Ganesh Naik", "Radha Srinivas", "Vinod Kumar", "Asha Reddy"
    ]
    
    genders = ["Male", "Female"]
    special_needs_options = ["None", "Wheelchair", "Visual Impairment", "Hearing Impairment", "Mobility Aid"]
    
    created_employees = []
    failed_employees = []
    
    employee_index = 0
    
    # Create 10 groups of 3 employees each
    for group_index in range(10):
        area = bangalore_areas[group_index]
        base_lat = area["lat"]
        base_lng = area["lng"]
        
        print(f"\n--- Creating Group {group_index + 1} in {area['area']} ---")
        
        for employee_in_group in range(3):
            # Generate coordinates within 1km radius of area center
            lat_offset = random.uniform(-0.009, 0.009)  # ~1km in degrees
            lng_offset = random.uniform(-0.009, 0.009)
            
            employee_data = {
                "name": names[employee_index],
                "email": f"{names[employee_index].lower().replace(' ', '.')}@company.com",
                "phone": f"+91{random.randint(7000000000, 9999999999)}",
                "alternate_phone": f"+91{random.randint(7000000000, 9999999999)}",
                "employee_code": f"EMP{employee_index + 1:03d}",
                "password": f"Pass@{random.randint(1000, 9999)}",
                "address": f"{random.randint(1, 999)}, {area['area']}, Bangalore, Karnataka, India",
                "latitude": round(base_lat + lat_offset, 6),
                "longitude": round(base_lng + lng_offset, 6),
                "gender": random.choice(genders),
                "team_id": 1,  # Assuming team IDs 1-5 exist
                "tenant_id": "SAM001",  # Update with actual tenant ID
                "is_active": random.choice([True, True, True, False]),  # 75% active
        
            }
            
            try:
                response = requests.post(ENDPOINT, headers=headers, json=employee_data)
                
                if response.status_code == 201:
                    result = response.json()
                    created_employees.append({
                        "employee_id": result.get("data", {}).get("employee", {}).get("employee_id"),
                        "name": employee_data["name"],
                        "area": area["area"],
                        "group": group_index + 1
                    })
                    print(f"✅ Created: {employee_data['name']} (ID: {result.get('data', {}).get('employee', {}).get('employee_id')})")
                else:
                    error_detail = response.json() if response.content else "Unknown error"
                    failed_employees.append({
                        "name": employee_data["name"],
                        "error": error_detail,
                        "status_code": response.status_code
                    })
                    print(f"❌ Failed: {employee_data['name']} - {response.status_code}: {error_detail}")
                    
            except requests.exceptions.RequestException as e:
                failed_employees.append({
                    "name": employee_data["name"],
                    "error": str(e),
                    "status_code": "Network Error"
                })
                print(f"❌ Network Error: {employee_data['name']} - {str(e)}")
            
            employee_index += 1
    
    # Summary
    print(f"\n{'='*50}")
    print(f"CREATION SUMMARY")
    print(f"{'='*50}")
    print(f"Total Employees Attempted: 30")
    print(f"Successfully Created: {len(created_employees)}")
    print(f"Failed: {len(failed_employees)}")
    
    if created_employees:
        print(f"\n✅ Successfully Created Employees:")
        for emp in created_employees:
            print(f"   - {emp['name']} (Group {emp['group']}, {emp['area']})")
    
    if failed_employees:
        print(f"\n❌ Failed Employees:")
        for emp in failed_employees:
            print(f"   - {emp['name']}: {emp['error']}")
    
    # Save results to file
    results = {
        "summary": {
            "total_attempted": 30,
            "successful": len(created_employees),
            "failed": len(failed_employees)
        },
        "created_employees": created_employees,
        "failed_employees": failed_employees
    }
    
    with open('employee_creation_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to 'employee_creation_results.json'")
    
    return results

if __name__ == "__main__":
    # Configuration reminder
    print("🔧 CONFIGURATION REQUIRED:")
    print("1. Update BASE_URL with your actual API endpoint")
    print("2. Replace 'YOUR_TOKEN_HERE' with a valid authorization token")
    print("3. Update 'tenant_123' with actual tenant ID")
    print("4. Ensure team IDs 1-5 exist in your database")
    print("5. Make sure you have proper permissions (employee.create)")
    print("\nPress Enter to continue or Ctrl+C to exit...")
    input()
    
    # Run the script
    results = create_employees_script()