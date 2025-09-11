-- Sample data for Fleet Manager

-- Admins
INSERT INTO admins (name, email, phone, password, is_active) VALUES
('Admin User', 'admin@fleetmanager.com', '9876543210', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('System Admin', 'sysadmin@fleetmanager.com', '9876543211', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Tech Support', 'support@fleetmanager.com', '9876543212', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true);

-- Teams
INSERT INTO teams (name, description) VALUES
('Engineering', 'Software development and engineering team'),
('Finance', 'Financial operations and accounting'),
('Human Resources', 'HR and people operations'),
('Marketing', 'Marketing and communications'),
('Sales', 'Sales and business development');

-- Tenants
INSERT INTO tenants (name, address, longitude, latitude, is_active) VALUES
('Headquarters', '123 Main St, City, Country', 77.123456, 28.123456, true),
('R&D Center', '456 Innovation Ave, Tech City, Country', 77.223456, 28.223456, true),
('Sales Office', '789 Business Blvd, Metro City, Country', 77.323456, 28.323456, true);

-- Vendors
INSERT INTO vendors (name, code, email, phone, is_active) VALUES
('Premium Cabs', 'PREM01', 'contact@premiumcabs.com', '9811111111', true),
('City Rides', 'CITY01', 'info@cityrides.com', '9822222222', true),
('Fleet Express', 'FLEET01', 'support@fleetexpress.com', '9833333333', true),
('Swift Transport', 'SWIFT01', 'info@swifttransport.com', '9844444444', true),
('Safe Journeys', 'SAFE01', 'bookings@safejourneys.com', '9855555555', true);

-- Vendor Users
INSERT INTO vendor_users (vendor_id, name, email, phone, password, is_active) VALUES
(1, 'John Manager', 'john@premiumcabs.com', '9711111111', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
(1, 'Alice Coordinator', 'alice@premiumcabs.com', '9711111112', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
(2, 'Bob Manager', 'bob@cityrides.com', '9722222221', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
(3, 'Carol Manager', 'carol@fleetexpress.com', '9733333331', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
(4, 'David Manager', 'david@swifttransport.com', '9744444441', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true);

-- Vehicle Types
INSERT INTO vehicle_types (vendor_id, name, description, is_active) VALUES
(1, 'Sedan', 'Standard 4-door sedan cars', true),
(1, 'SUV', 'Sport utility vehicles', true),
(2, 'Sedan', 'Compact and mid-size sedans', true),
(2, 'Hatchback', 'Small hatchback cars', true),
(3, 'Sedan', 'Premium sedans', true),
(3, 'Van', 'Passenger vans', true),
(4, 'SUV', 'Spacious SUVs', true),
(5, 'Sedan', 'Economy sedans', true),
(5, 'Premium', 'Luxury vehicles', true);

-- Shifts
INSERT INTO shifts (shift_code, log_type, shift_time, pickup_type, gender, waiting_time_minutes, is_active) VALUES
('MORN_IN', 'IN', '08:00:00', 'Pickup', NULL, 15, true),
('MORN_OUT', 'OUT', '17:00:00', 'Pickup', NULL, 15, true),
('EVE_IN', 'IN', '14:00:00', 'Pickup', NULL, 15, true),
('EVE_OUT', 'OUT', '23:00:00', 'Pickup', NULL, 15, true),
('NIGHT_IN', 'IN', '22:00:00', 'Pickup', NULL, 15, true),
('NIGHT_OUT', 'OUT', '07:00:00', 'Pickup', NULL, 15, true),
('WMN_MORN_IN', 'IN', '08:00:00', 'Pickup', 'Female', 15, true),
('WMN_MORN_OUT', 'OUT', '17:00:00', 'Pickup', 'Female', 15, true),
('NODAL_IN', 'IN', '09:00:00', 'Nodal', NULL, 0, true),
('NODAL_OUT', 'OUT', '18:00:00', 'Nodal', NULL, 0, true);

-- Drivers (10 entries)
INSERT INTO drivers (vendor_id, name, code, email, phone, gender, password, date_of_joining, date_of_birth,
                   permanent_address, current_address, license_number, license_expiry_date,
                   badge_number, is_active) VALUES
(1, 'Rajesh Kumar', 'D1001', 'rajesh@example.com', '9911111111', 'Male', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-01-15', '1985-05-10', 'Village Jharkhand', 'Delhi NCR', 'DL-1420110012345', '2026-05-10', 'BDGE1001', true),
(1, 'Manoj Singh', 'D1002', 'manoj@example.com', '9911111112', 'Male', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-02-10', '1988-07-15', 'Patna, Bihar', 'Delhi NCR', 'DL-1420110012346', '2025-07-15', 'BDGE1002', true),
(2, 'Suresh Yadav', 'D2001', 'suresh@example.com', '9922222221', 'Male', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2021-11-05', '1990-03-20', 'Lucknow, UP', 'Delhi NCR', 'DL-1420110012347', '2026-03-20', 'BDGE2001', true),
(2, 'Ramesh Sharma', 'D2002', 'ramesh@example.com', '9922222222', 'Male', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-03-15', '1987-11-25', 'Jaipur, Rajasthan', 'Delhi NCR', 'DL-1420110012348', '2025-11-25', 'BDGE2002', true),
(3, 'Amit Verma', 'D3001', 'amit@example.com', '9933333331', 'Male', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-05-12', '1992-01-30', 'Kanpur, UP', 'Delhi NCR', 'DL-1420110012349', '2026-01-30', 'BDGE3001', true),
(3, 'Pooja Devi', 'D3002', 'pooja@example.com', '9933333332', 'Female', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-06-18', '1991-09-12', 'Delhi', 'Delhi NCR', 'DL-1420110012350', '2025-09-12', 'BDGE3002', true),
(4, 'Vijay Kumar', 'D4001', 'vijay@example.com', '9944444441', 'Male', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-04-05', '1986-08-14', 'Bhopal, MP', 'Delhi NCR', 'DL-1420110012351', '2026-08-14', 'BDGE4001', true),
(5, 'Sanjay Gupta', 'D5001', 'sanjay@example.com', '9955555551', 'Male', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-01-20', '1989-12-05', 'Dehradun, Uttarakhand', 'Delhi NCR', 'DL-1420110012352', '2025-12-05', 'BDGE5001', true),
(5, 'Neha Singh', 'D5002', 'neha@example.com', '9955555552', 'Female', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-07-10', '1993-04-18', 'Meerut, UP', 'Delhi NCR', 'DL-1420110012353', '2026-04-18', 'BDGE5002', true),
(1, 'Ravi Prakash', 'D1003', 'ravi@example.com', '9911111113', 'Male', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
   '2022-08-05', '1984-06-22', 'Agra, UP', 'Delhi NCR', 'DL-1420110012354', '2025-06-22', 'BDGE1003', true);

-- Vehicles (10 entries)
INSERT INTO vehicles (vehicle_type_id, vendor_id, driver_id, rc_number, rc_expiry_date, description, 
                    insurance_expiry_date, is_active) VALUES
(1, 1, 1, 'DL01AB1234', '2026-12-31', 'White Toyota Etios', '2024-12-31', true),
(1, 1, 2, 'DL01CD5678', '2026-11-30', 'Silver Honda City', '2024-11-30', true),
(3, 2, 3, 'DL02EF9012', '2027-01-15', 'White Swift Dzire', '2025-01-15', true),
(4, 2, 4, 'DL02GH3456', '2026-10-25', 'Red Maruti Swift', '2024-10-25', true),
(5, 3, 5, 'DL03IJ7890', '2027-02-28', 'Black Honda Accord', '2025-02-28', true),
(6, 3, 6, 'DL03KL1234', '2027-03-15', 'White Toyota Innova', '2025-03-15', true),
(7, 4, 7, 'DL04MN5678', '2026-09-20', 'Grey Hyundai Creta', '2024-09-20', true),
(8, 5, 8, 'DL05OP9012', '2026-08-10', 'Blue Honda Amaze', '2024-08-10', true),
(9, 5, 9, 'DL05QR3456', '2027-05-12', 'Black Mercedes C-Class', '2025-05-12', true),
(1, 1, 10, 'DL01ST7890', '2027-04-05', 'Grey Maruti Ciaz', '2025-04-05', true);

-- Employees (15 entries)
INSERT INTO employees (name, employee_code, email, password, team_id, phone, address, gender, is_active) VALUES
('Rahul Sharma', 'EMP001', 'rahul@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 1, '9811000001', 'Sector 62, Noida', 'Male', true),
('Priya Singh', 'EMP002', 'priya@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 1, '9811000002', 'Rohini, Delhi', 'Female', true),
('Amit Kumar', 'EMP003', 'amit@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 2, '9811000003', 'Sector 18, Noida', 'Male', true),
('Sneha Gupta', 'EMP004', 'sneha@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 2, '9811000004', 'Malviya Nagar, Delhi', 'Female', true),
('Vivek Mishra', 'EMP005', 'vivek@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 3, '9811000005', 'Greater Kailash, Delhi', 'Male', true),
('Neha Patel', 'EMP006', 'neha@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 3, '9811000006', 'Indirapuram, Ghaziabad', 'Female', true),
('Aditya Verma', 'EMP007', 'aditya@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 4, '9811000007', 'DLF Cybercity, Gurgaon', 'Male', true),
('Anjali Saxena', 'EMP008', 'anjali@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 4, '9811000008', 'Vasant Kunj, Delhi', 'Female', true),
('Nitin Joshi', 'EMP009', 'nitin@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 5, '9811000009', 'Dwarka, Delhi', 'Male', true),
('Kavita Sharma', 'EMP010', 'kavita@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 5, '9811000010', 'Sector 45, Noida', 'Female', true),
('Deepak Bansal', 'EMP011', 'deepak@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 1, '9811000011', 'Pitampura, Delhi', 'Male', true),
('Ritu Agarwal', 'EMP012', 'ritu@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 2, '9811000012', 'Mayur Vihar, Delhi', 'Female', true),
('Saurabh Kapoor', 'EMP013', 'saurabh@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 3, '9811000013', 'Sector 29, Gurgaon', 'Male', true),
('Meera Reddy', 'EMP014', 'meera@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 4, '9811000014', 'Lajpat Nagar, Delhi', 'Female', true),
('Rajat Mehta', 'EMP015', 'rajat@company.com', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 
 5, '9811000015', 'Vaishali, Ghaziabad', 'Male', true);

-- Weekoff configs (15 entries to match employees)
INSERT INTO weekoff_configs (employee_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday) VALUES
(1, false, false, false, false, false, true, true),
(2, false, false, false, false, false, true, true),
(3, false, false, false, false, false, true, true),
(4, false, false, false, false, false, true, true),
(5, false, false, false, false, false, true, true),
(6, false, false, false, false, false, true, true),
(7, false, false, false, false, false, true, true),
(8, false, false, false, false, false, true, true),
(9, false, false, false, false, false, true, true),
(10, false, false, false, false, false, true, true),
(11, false, false, false, false, false, true, true),
(12, false, false, false, false, false, true, true),
(13, false, false, false, false, false, true, true),
(14, false, false, false, false, false, true, true),
(15, false, false, false, false, false, true, true);

-- Bookings (at least 20 entries)
INSERT INTO bookings (employee_id, shift_id, booking_date, pickup_latitude, pickup_longitude, 
                     pickup_location, drop_latitude, drop_longitude, drop_location, status, team_id) VALUES
-- Current day bookings
(1, 1, CURRENT_DATE, 28.6139, 77.2090, 'Sector 62, Noida', 28.7041, 77.1025, 'Office', 'Confirmed', 1),
(2, 1, CURRENT_DATE, 28.7519, 77.1173, 'Rohini, Delhi', 28.7041, 77.1025, 'Office', 'Confirmed', 1),
(3, 1, CURRENT_DATE, 28.5706, 77.3206, 'Sector 18, Noida', 28.7041, 77.1025, 'Office', 'Confirmed', 2),
(4, 2, CURRENT_DATE, 28.5365, 77.2153, 'Malviya Nagar, Delhi', 28.5706, 77.3206, 'Home', 'Pending', 2),
(5, 1, CURRENT_DATE, 28.5544, 77.2477, 'Greater Kailash, Delhi', 28.7041, 77.1025, 'Office', 'Confirmed', 3),

-- Next day bookings
(6, 1, CURRENT_DATE + INTERVAL '1 day', 28.6463, 77.3609, 'Indirapuram, Ghaziabad', 28.7041, 77.1025, 'Office', 'Pending', 3),
(7, 1, CURRENT_DATE + INTERVAL '1 day', 28.4595, 77.0266, 'DLF Cybercity, Gurgaon', 28.7041, 77.1025, 'Office', 'Pending', 4),
(8, 2, CURRENT_DATE + INTERVAL '1 day', 28.5362, 77.1590, 'Vasant Kunj, Delhi', 28.4595, 77.0266, 'Home', 'Pending', 4),
(9, 1, CURRENT_DATE + INTERVAL '1 day', 28.6147, 77.0401, 'Dwarka, Delhi', 28.7041, 77.1025, 'Office', 'Pending', 5),
(10, 2, CURRENT_DATE + INTERVAL '1 day', 28.5336, 77.3891, 'Sector 45, Noida', 28.6147, 77.0401, 'Home', 'Pending', 5),

-- Past bookings
(11, 1, CURRENT_DATE - INTERVAL '1 day', 28.7292, 77.1250, 'Pitampura, Delhi', 28.7041, 77.1025, 'Office', 'Completed', 1),
(12, 2, CURRENT_DATE - INTERVAL '1 day', 28.6073, 77.2915, 'Mayur Vihar, Delhi', 28.7292, 77.1250, 'Home', 'Completed', 2),
(13, 1, CURRENT_DATE - INTERVAL '1 day', 28.4691, 77.0926, 'Sector 29, Gurgaon', 28.7041, 77.1025, 'Office', 'Completed', 3),
(14, 2, CURRENT_DATE - INTERVAL '1 day', 28.5709, 77.2373, 'Lajpat Nagar, Delhi', 28.5709, 77.2373, 'Home', 'Completed', 4),
(15, 1, CURRENT_DATE - INTERVAL '1 day', 28.6720, 77.3588, 'Vaishali, Ghaziabad', 28.7041, 77.1025, 'Office', 'Completed', 5),

-- More past bookings
(1, 2, CURRENT_DATE - INTERVAL '2 days', 28.7041, 77.1025, 'Office', 28.6139, 77.2090, 'Home', 'Completed', 1),
(2, 2, CURRENT_DATE - INTERVAL '2 days', 28.7041, 77.1025, 'Office', 28.7519, 77.1173, 'Home', 'Completed', 1),
(3, 2, CURRENT_DATE - INTERVAL '2 days', 28.7041, 77.1025, 'Office', 28.5706, 77.3206, 'Home', 'Completed', 2),
(4, 1, CURRENT_DATE - INTERVAL '2 days', 28.5365, 77.2153, 'Malviya Nagar, Delhi', 28.7041, 77.1025, 'Office', 'Canceled', 2),
(5, 2, CURRENT_DATE - INTERVAL '2 days', 28.7041, 77.1025, 'Office', 28.5544, 77.2477, 'Home', 'Completed', 3);

-- Routes (5 entries)
INSERT INTO routes (shift_id, route_code, status, planned_distance_km, planned_duration_minutes, 
                   assigned_vendor_id, assigned_vehicle_id, assigned_driver_id, is_active) VALUES
(1, 'RT001-'||to_char(CURRENT_DATE, 'YYYYMMDD'), 'Completed', 18.5, 45, 1, 1, 1, true),
(2, 'RT002-'||to_char(CURRENT_DATE, 'YYYYMMDD'), 'Planned', 20.3, 55, NULL, NULL, NULL, true),
(1, 'RT003-'||to_char(CURRENT_DATE + INTERVAL '1 day', 'YYYYMMDD'), 'Planned', 22.1, 60, NULL, NULL, NULL, true),
(2, 'RT004-'||to_char(CURRENT_DATE + INTERVAL '1 day', 'YYYYMMDD'), 'Planned', 19.7, 50, NULL, NULL, NULL, true),
(1, 'RT005-'||to_char(CURRENT_DATE - INTERVAL '1 day', 'YYYYMMDD'), 'Completed', 21.5, 58, 2, 3, 3, true);

-- Route Bookings (link routes to bookings)
-- Route 1 (Completed today's morning route)
INSERT INTO route_bookings (route_id, booking_id, planned_eta_minutes, actual_arrival_time, actual_departure_time) VALUES
(1, 1, 15, CURRENT_TIMESTAMP - INTERVAL '10 hours', CURRENT_TIMESTAMP - INTERVAL '9 hours 50 minutes'),
(1, 2, 25, CURRENT_TIMESTAMP - INTERVAL '9 hours 40 minutes', CURRENT_TIMESTAMP - INTERVAL '9 hours 30 minutes'),
(1, 3, 35, CURRENT_TIMESTAMP - INTERVAL '9 hours 20 minutes', CURRENT_TIMESTAMP - INTERVAL '9 hours 10 minutes'),
(1, 5, 45, CURRENT_TIMESTAMP - INTERVAL '9 hours', CURRENT_TIMESTAMP - INTERVAL '8 hours 50 minutes');

-- Route 2 (Planned today's evening route)
INSERT INTO route_bookings (route_id, booking_id, planned_eta_minutes) VALUES
(2, 4, 15);

-- Route 3 (Tomorrow's morning route)
INSERT INTO route_bookings (route_id, booking_id, planned_eta_minutes) VALUES
(3, 6, 15),
(3, 7, 25),
(3, 9, 35);

-- Route 4 (Tomorrow's evening route)
INSERT INTO route_bookings (route_id, booking_id, planned_eta_minutes) VALUES
(4, 8, 15),
(4, 10, 30);

-- Route 5 (Yesterday's morning route)
INSERT INTO route_bookings (route_id, booking_id, planned_eta_minutes, actual_arrival_time, actual_departure_time) VALUES
(5, 11, 15, CURRENT_TIMESTAMP - INTERVAL '34 hours', CURRENT_TIMESTAMP - INTERVAL '33 hours 50 minutes'),
(5, 13, 30, CURRENT_TIMESTAMP - INTERVAL '33 hours 40 minutes', CURRENT_TIMESTAMP - INTERVAL '33 hours 30 minutes'),
(5, 15, 45, CURRENT_TIMESTAMP - INTERVAL '33 hours 20 minutes', CURRENT_TIMESTAMP - INTERVAL '33 hours 10 minutes');
