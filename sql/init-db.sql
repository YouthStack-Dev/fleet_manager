-- Combined initialization file for schema and data

-- Initialize database schema based on new_db.sql
CREATE SCHEMA IF NOT EXISTS public;

-- Create ENUM types
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'booking_status_enum') THEN
        CREATE TYPE public."booking_status_enum" AS ENUM (
            'Pending',
            'Confirmed',
            'Ongoing',
            'Completed',
            'Canceled');
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'gender_enum') THEN
        CREATE TYPE public."gender_enum" AS ENUM (
            'Male',
            'Female',
            'Other');
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pickup_type_enum') THEN
        CREATE TYPE public."pickup_type_enum" AS ENUM (
            'Pickup',
            'Nodal');
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'shift_log_type_enum') THEN
        CREATE TYPE public."shift_log_type_enum" AS ENUM (
            'IN',
            'OUT');
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'verification_status_enum') THEN
        CREATE TYPE public."verification_status_enum" AS ENUM (
            'Pending',
            'Approved',
            'Rejected');
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'route_status_enum') THEN
        CREATE TYPE public."route_status_enum" AS ENUM (
            'Planned',
            'Assigned',
            'InProgress',
            'Completed',
            'Cancelled');
    END IF;
END $$;

-- Create tables
CREATE TABLE IF NOT EXISTS admins ( 
    admin_id SERIAL PRIMARY KEY, 
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE,
    password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    team_id SERIAL PRIMARY KEY,
    name VARCHAR(150) UNIQUE NOT NULL,
    description TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id SERIAL PRIMARY KEY,
    name VARCHAR(150) UNIQUE NOT NULL,
    address VARCHAR(255) NULL,
    longitude NUMERIC(9, 6) NULL,
    latitude NUMERIC(9, 6) NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS vendors (
    vendor_id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    code VARCHAR(50) UNIQUE NULL,
    email VARCHAR(150) UNIQUE NULL,
    phone VARCHAR(20) UNIQUE NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS shifts (
    shift_id SERIAL PRIMARY KEY,
    shift_code VARCHAR(50) UNIQUE NOT NULL,
    log_type public."shift_log_type_enum" NOT NULL,
    shift_time TIME NOT NULL,
    pickup_type public."pickup_type_enum" NULL,
    gender public."gender_enum" NULL,
    waiting_time_minutes INTEGER DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL,
    name VARCHAR(150) NOT NULL,
    code VARCHAR(50) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    gender public."gender_enum" NULL,
    password VARCHAR(255) NOT NULL,
    date_of_joining DATE NULL,
    date_of_birth DATE NULL,
    permanent_address TEXT NULL,
    current_address TEXT NULL,
    bg_verify_status public."verification_status_enum" NULL,
    bg_verify_date DATE NULL,
    bg_verify_url TEXT NULL,
    police_verify_status public."verification_status_enum" NULL,
    police_verify_date DATE NULL,
    police_verify_url TEXT NULL,
    medical_verify_status public."verification_status_enum" NULL,
    medical_verify_date DATE NULL,
    medical_verify_url TEXT NULL,
    training_verify_status public."verification_status_enum" NULL,
    training_verify_date DATE NULL,
    training_verify_url TEXT NULL,
    eye_verify_status public."verification_status_enum" NULL,
    eye_verify_date DATE NULL,
    eye_verify_url TEXT NULL,
    license_number VARCHAR(100) NULL,
    license_expiry_date DATE NULL,
    induction_status public."verification_status_enum" NULL,
    induction_date DATE NULL,
    induction_url TEXT NULL,
    badge_number VARCHAR(100) UNIQUE NULL,
    badge_expiry_date DATE NULL,
    badge_url TEXT NULL,
    alt_govt_id_number VARCHAR(20) NULL,
    alt_govt_id_type VARCHAR(50) NULL,
    alt_govt_id_url TEXT NULL,
    photo_url TEXT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT drivers_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    employee_code VARCHAR(50) UNIQUE NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    team_id INTEGER NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    alternate_phone VARCHAR(20) NULL,
    special_needs TEXT NULL,
    special_needs_start_date DATE NULL,
    special_needs_end_date DATE NULL,
    address TEXT NULL,
    latitude NUMERIC(9, 6) NULL,
    longitude NUMERIC(9, 6) NULL,
    gender public."gender_enum" NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT employees_team_id_fkey FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS vehicle_types (
    vehicle_type_id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT vehicle_types_vendor_id_name_key UNIQUE (vendor_id, name),
    CONSTRAINT vehicle_types_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id SERIAL PRIMARY KEY,
    vehicle_type_id INTEGER NOT NULL,
    vendor_id INTEGER NOT NULL,
    driver_id INTEGER NULL,
    rc_number VARCHAR(100) UNIQUE NOT NULL,
    rc_expiry_date DATE NULL,
    description TEXT NULL,
    puc_expiry_date DATE NULL,
    puc_url TEXT NULL,
    fitness_expiry_date DATE NULL,
    fitness_url TEXT NULL,
    tax_receipt_date DATE NULL,
    tax_receipt_url TEXT NULL,
    insurance_expiry_date DATE NULL,
    insurance_url TEXT NULL,
    permit_expiry_date DATE NULL,
    permit_url TEXT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT vehicles_driver_id_fkey FOREIGN KEY (driver_id) REFERENCES drivers(driver_id) ON DELETE SET NULL,
    CONSTRAINT vehicles_vehicle_type_id_fkey FOREIGN KEY (vehicle_type_id) REFERENCES vehicle_types(vehicle_type_id) ON DELETE CASCADE,
    CONSTRAINT vehicles_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vendor_users (
    vendor_user_id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT vendor_users_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weekoff_configs (
    weekoff_id SERIAL PRIMARY KEY,
    employee_id INTEGER UNIQUE NOT NULL,
    monday BOOLEAN DEFAULT FALSE NOT NULL,
    tuesday BOOLEAN DEFAULT FALSE NOT NULL,
    wednesday BOOLEAN DEFAULT FALSE NOT NULL,
    thursday BOOLEAN DEFAULT FALSE NOT NULL,
    friday BOOLEAN DEFAULT FALSE NOT NULL,
    saturday BOOLEAN DEFAULT FALSE NOT NULL,
    sunday BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT weekoff_configs_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bookings (
    booking_id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    shift_id INTEGER NULL,
    booking_date DATE NOT NULL,
    pickup_latitude DOUBLE PRECISION NULL,
    pickup_longitude DOUBLE PRECISION NULL,
    pickup_location VARCHAR(255) NULL,
    drop_latitude DOUBLE PRECISION NULL,
    drop_longitude DOUBLE PRECISION NULL,
    drop_location VARCHAR(255) NULL,
    status public."booking_status_enum" DEFAULT 'Pending'::booking_status_enum NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    team_id INTEGER NULL,
    CONSTRAINT bookings_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT bookings_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE,
    CONSTRAINT bookings_team_id_fkey FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS routes (
    route_id SERIAL PRIMARY KEY,
    shift_id INTEGER NULL,
    route_code VARCHAR(100) UNIQUE NOT NULL,
    status public."route_status_enum" DEFAULT 'Planned'::route_status_enum NOT NULL,
    planned_distance_km DOUBLE PRECISION NULL,
    planned_duration_minutes INTEGER NULL,
    actual_distance_km DOUBLE PRECISION NULL,
    actual_duration_minutes INTEGER NULL,
    actual_start_time TIMESTAMP NULL,
    actual_end_time TIMESTAMP NULL,
    optimized_polyline TEXT NULL,
    assigned_vendor_id INTEGER NULL,
    assigned_vehicle_id INTEGER NULL,
    assigned_driver_id INTEGER NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT routes_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE,
    CONSTRAINT routes_assigned_vendor_id_fkey FOREIGN KEY (assigned_vendor_id) REFERENCES vendors(vendor_id) ON DELETE SET NULL,
    CONSTRAINT routes_assigned_vehicle_id_fkey FOREIGN KEY (assigned_vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE SET NULL,
    CONSTRAINT routes_assigned_driver_id_fkey FOREIGN KEY (assigned_driver_id) REFERENCES drivers(driver_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_routes_shift_status ON routes (shift_id, status);

CREATE TABLE IF NOT EXISTS route_bookings (
    route_booking_id SERIAL PRIMARY KEY,
    route_id INTEGER NOT NULL,
    booking_id INTEGER NOT NULL,
    planned_eta_minutes INTEGER NULL,
    actual_arrival_time TIMESTAMP NULL,
    actual_departure_time TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT route_bookings_route_id_fkey FOREIGN KEY (route_id) REFERENCES routes(route_id) ON DELETE CASCADE,
    CONSTRAINT route_bookings_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_route_bookings_route ON route_bookings (route_id);

-- Sample data insertion

-- Teams
INSERT INTO teams (name, description)
VALUES
('Engineering', 'Software development and engineering team'),
('Finance', 'Financial operations and accounting'),
('Human Resources', 'HR and people operations'),
('Marketing', 'Marketing and communications'),
('Sales', 'Sales and business development'),
('Operations', 'Day-to-day business operations'),
('Customer Support', 'Customer support and helpdesk'),
('Quality Assurance', 'Testing and quality assurance'),
('Product Management', 'Product planning and strategy'),
('Design', 'UI/UX and product design'),
('IT', 'Information technology and infrastructure'),
('Legal', 'Legal and compliance team'),
('Procurement', 'Purchasing and supply management'),
('Logistics', 'Logistics and fleet operations'),
('Security', 'Security and risk management'),
('Research', 'Research and development team'),
('Data Science', 'Data analytics and insights'),
('Partnerships', 'Business partnerships and alliances'),
('Training', 'Employee training and development'),
('Field Operations', 'On-site and field operations')
ON CONFLICT (name) DO NOTHING;

-- Employees
INSERT INTO employees (name, email, phone, employee_code, team_id, password, is_active) VALUES
('Anil Kumar', 'anil.kumar@fleet.com', '9500000001', 'EMP001', 1, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Bhavna Singh', 'bhavna.singh@fleet.com', '9500000002', 'EMP002', 2, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Chetan Rao', 'chetan.rao@fleet.com', '9500000003', 'EMP003', 3, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Deepa Yadav', 'deepa.yadav@fleet.com', '9500000004', 'EMP004', 4, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Eshan Gupta', 'eshan.gupta@fleet.com', '9500000005', 'EMP005', 5, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Farah Khan', 'farah.khan@fleet.com', '9500000006', 'EMP006', 6, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Ganesh Joshi', 'ganesh.joshi@fleet.com', '9500000007', 'EMP007', 7, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Harsha Patel', 'harsha.patel@fleet.com', '9500000008', 'EMP008', 8, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Imran Ali', 'imran.ali@fleet.com', '9500000009', 'EMP009', 9, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Jaya Mishra', 'jaya.mishra@fleet.com', '9500000010', 'EMP010', 10, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Kunal Kapoor', 'kunal.kapoor@fleet.com', '9500000011', 'EMP011', 11, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Lata Sharma', 'lata.sharma@fleet.com', '9500000012', 'EMP012', 12, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Mohan Reddy', 'mohan.reddy@fleet.com', '9500000013', 'EMP013', 13, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Neeraj Jain', 'neeraj.jain@fleet.com', '9500000014', 'EMP014', 14, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Om Prakash', 'om.prakash@fleet.com', '9500000015', 'EMP015', 15, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Priti Desai', 'priti.desai@fleet.com', '9500000016', 'EMP016', 16, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Qasim Khan', 'qasim.khan@fleet.com', '9500000017', 'EMP017', 17, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Rohit Verma', 'rohit.verma@fleet.com', '9500000018', 'EMP018', 18, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Sonal Singh', 'sonal.singh@fleet.com', '9500000019', 'EMP019', 19, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Tina Dutta', 'tina.dutta@fleet.com', '9500000020', 'EMP020', 20, '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true);
-- ON CONFLICT (email) DO NOTHING;

-- Admins
INSERT INTO admins (name, email, phone, password, is_active) 
VALUES
('Admin User', 'admin@fleetmanager.com', '9876543210', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('System Admin', 'sysadmin@fleetmanager.com', '9876543211', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Tech Support', 'support@fleetmanager.com', '9876543212', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Alice Johnson', 'alice.johnson@fleetmanager.com', '9876543213', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Bob Smith', 'bob.smith@fleetmanager.com', '9876543214', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Carol White', 'carol.white@fleetmanager.com', '9876543215', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('David Brown', 'david.brown@fleetmanager.com', '9876543216', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Eve Black', 'eve.black@fleetmanager.com', '9876543217', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Frank Green', 'frank.green@fleetmanager.com', '9876543218', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Grace Lee', 'grace.lee@fleetmanager.com', '9876543219', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Henry King', 'henry.king@fleetmanager.com', '9876543220', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Ivy Scott', 'ivy.scott@fleetmanager.com', '9876543221', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Jack Turner', 'jack.turner@fleetmanager.com', '9876543222', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Karen Harris', 'karen.harris@fleetmanager.com', '9876543223', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Leo Walker', 'leo.walker@fleetmanager.com', '9876543224', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Mia Young', 'mia.young@fleetmanager.com', '9876543225', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Noah Hill', 'noah.hill@fleetmanager.com', '9876543226', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Olivia Adams', 'olivia.adams@fleetmanager.com', '9876543227', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Paul Nelson', 'paul.nelson@fleetmanager.com', '9876543228', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Quincy Baker', 'quincy.baker@fleetmanager.com', '9876543229', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true),
('Rachel Carter', 'rachel.carter@fleetmanager.com', '9876543230', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true)
ON CONFLICT (email) DO NOTHING;

-- Tenants
INSERT INTO tenants (name, address, longitude, latitude, is_active)
VALUES
('Headquarters', '123 Main St, City, Country', 77.123456, 28.123456, true),
('R&D Center', '456 Innovation Ave, Tech City, Country', 77.223456, 28.223456, true),
('Sales Office', '789 Business Blvd, Metro City, Country', 77.323456, 28.323456, true),
('Logistics Hub', '101 Logistic Pkwy, City, Country', 77.423456, 28.423456, true),
('Regional Office North', '202 North St, City, Country', 77.523456, 28.523456, true),
('Regional Office South', '303 South St, City, Country', 77.623456, 28.623456, true),
('Regional Office East', '404 East St, City, Country', 77.723456, 28.723456, true),
('Regional Office West', '505 West St, City, Country', 77.823456, 28.823456, true),
('Warehouse Central', '606 Central Ave, City, Country', 77.923456, 28.923456, true),
('Fleet Garage', '707 Garage Rd, City, Country', 78.023456, 29.023456, true),
('Support Center', '808 Support Blvd, City, Country', 78.123456, 29.123456, true),
('Tech Park', '909 Tech Park, City, Country', 78.223456, 29.223456, true),
('Training Center', '111 Training Dr, City, Country', 78.323456, 29.323456, true),
('Operations Base', '222 Operations St, City, Country', 78.423456, 29.423456, true),
('Data Center', '333 Data St, City, Country', 78.523456, 29.523456, true),
('Remote Office 1', '444 Remote Rd, City, Country', 78.623456, 29.623456, true),
('Remote Office 2', '555 Remote Rd, City, Country', 78.723456, 29.723456, true),
('Service Depot', '666 Service Ln, City, Country', 78.823456, 29.823456, true),
('Maintenance Facility', '777 Maintenance Ave, City, Country', 78.923456, 29.923456, true),
('Innovation Lab', '888 Innovation Blvd, City, Country', 79.023456, 30.023456, true)
ON CONFLICT (name) DO NOTHING;

-- Vendors
INSERT INTO vendors (name, code, email, phone, is_active)
VALUES
('Premium Cabs', 'PREM01', 'contact@premiumcabs.com', '9811111111', true),
('City Rides', 'CITY01', 'info@cityrides.com', '9822222222', true),
('Fleet Express', 'FLEET01', 'support@fleetexpress.com', '9833333333', true),
('Swift Transport', 'SWIFT01', 'info@swifttransport.com', '9844444444', true),
('Safe Journeys', 'SAFE01', 'bookings@safejourneys.com', '9855555555', true),
('Urban Wheels', 'URBAN01', 'contact@urbanwheels.com', '9866666666', true),
('Metro Taxis', 'METRO01', 'info@metrotaxis.com', '9877777777', true),
('Elite Cars', 'ELITE01', 'support@elitecars.com', '9888888888', true),
('Royal Rides', 'ROYAL01', 'info@royalrides.com', '9899999999', true),
('Speedy Travels', 'SPEED01', 'book@speedytravels.com', '9800000000', true),
('Budget Cabs', 'BUDGET01', 'service@budgetcabs.com', '9801111111', true),
('Star Cabs', 'STAR01', 'hello@starcabs.com', '9802222222', true),
('Go Taxi', 'GO01', 'info@gotaxi.com', '9803333333', true),
('Quick Wheels', 'QUICK01', 'ride@quickwheels.com', '9804444444', true),
('Easy Rides', 'EASY01', 'easy@easyrides.com', '9805555555', true),
('Comfort Travels', 'COMFORT01', 'support@comforttravels.com', '9806666666', true),
('Reliable Transport', 'RELIABLE01', 'contact@reliabletransport.com', '9807777777', true),
('Advance Cabs', 'ADVANCE01', 'advance@advancecabs.com', '9808888888', true),
('Transport Hub', 'HUB01', 'info@transporthub.com', '9809999999', true),
('Classic Cars', 'CLASSIC01', 'classic@classiccars.com', '9810000000', true)
ON CONFLICT (code) DO NOTHING;

-- Shifts
INSERT INTO shifts (shift_code, log_type, shift_time, pickup_type, gender, waiting_time_minutes, is_active) 
VALUES
('MORN_IN', 'IN', '08:00:00', 'Pickup', NULL, 15, true),
('MORN_OUT', 'OUT', '17:00:00', 'Pickup', NULL, 15, true),
('EVE_IN', 'IN', '14:00:00', 'Pickup', NULL, 15, true),
('EVE_OUT', 'OUT', '23:00:00', 'Pickup', NULL, 15, true),
('NIGHT_IN', 'IN', '22:00:00', 'Pickup', NULL, 15, true),
('NIGHT_OUT', 'OUT', '07:00:00', 'Pickup', NULL, 15, true),
('WMN_MORN_IN', 'IN', '08:00:00', 'Pickup', 'Female', 15, true),
('WMN_MORN_OUT', 'OUT', '17:00:00', 'Pickup', 'Female', 15, true),
('NODAL_IN', 'IN', '09:00:00', 'Nodal', NULL, 0, true),
('NODAL_OUT', 'OUT', '18:00:00', 'Nodal', NULL, 0, true),
('MIDDAY_IN', 'IN', '12:00:00', 'Pickup', NULL, 10, true),
('MIDDAY_OUT', 'OUT', '13:00:00', 'Pickup', NULL, 10, true),
('LATE_NIGHT_IN', 'IN', '23:30:00', 'Pickup', NULL, 20, true),
('LATE_NIGHT_OUT', 'OUT', '06:30:00', 'Pickup', NULL, 20, true),
('EARLY_MORN_IN', 'IN', '05:00:00', 'Pickup', NULL, 10, true),
('EARLY_MORN_OUT', 'OUT', '06:00:00', 'Pickup', NULL, 10, true),
('WMN_EVE_IN', 'IN', '14:00:00', 'Pickup', 'Female', 15, true),
('WMN_EVE_OUT', 'OUT', '23:00:00', 'Pickup', 'Female', 15, true),
('WMN_NIGHT_IN', 'IN', '22:00:00', 'Pickup', 'Female', 15, true),
('WMN_NIGHT_OUT', 'OUT', '07:00:00', 'Pickup', 'Female', 15, true)
ON CONFLICT (shift_code) DO NOTHING;

-- Vendor Users
INSERT INTO vendor_users (vendor_id, name, email, phone, password, is_active)
SELECT v.vendor_id, 'John Manager', 'john@premiumcabs.com', '9711111111', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'PREM01'
UNION ALL
SELECT v.vendor_id, 'Alice Supervisor', 'alice@cityrides.com', '9722222222', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'CITY01'
UNION ALL
SELECT v.vendor_id, 'Bob Coordinator', 'bob@fleetexpress.com', '9733333333', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'FLEET01'
UNION ALL
SELECT v.vendor_id, 'Carol Incharge', 'carol@swifttransport.com', '9744444444', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'SWIFT01'
UNION ALL
SELECT v.vendor_id, 'David Lead', 'david@safejourneys.com', '9755555555', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'SAFE01'
UNION ALL
SELECT v.vendor_id, 'Ella Admin', 'ella@urbanwheels.com', '9766666666', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'URBAN01'
UNION ALL
SELECT v.vendor_id, 'Frank Supervisor', 'frank@metrotaxis.com', '9777777777', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'METRO01'
UNION ALL
SELECT v.vendor_id, 'Grace Coordinator', 'grace@elitecars.com', '9788888888', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'ELITE01'
UNION ALL
SELECT v.vendor_id, 'Henry Manager', 'henry@royalrides.com', '9799999999', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'ROYAL01'
UNION ALL
SELECT v.vendor_id, 'Ivy Lead', 'ivy@speedytravels.com', '9700000000', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'SPEED01'
UNION ALL
SELECT v.vendor_id, 'Jack Admin', 'jack@budgetcabs.com', '9701111111', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'BUDGET01'
UNION ALL
SELECT v.vendor_id, 'Karen Supervisor', 'karen@starcabs.com', '9702222222', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'STAR01'
UNION ALL
SELECT v.vendor_id, 'Leo Coordinator', 'leo@gotaxi.com', '9703333333', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'GO01'
UNION ALL
SELECT v.vendor_id, 'Mia Manager', 'mia@quickwheels.com', '9704444444', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'QUICK01'
UNION ALL
SELECT v.vendor_id, 'Noah Lead', 'noah@easyrides.com', '9705555555', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'EASY01'
UNION ALL
SELECT v.vendor_id, 'Olivia Admin', 'olivia@comforttravels.com', '9706666666', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'COMFORT01'
UNION ALL
SELECT v.vendor_id, 'Paul Supervisor', 'paul@reliabletransport.com', '9707777777', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'RELIABLE01'
UNION ALL
SELECT v.vendor_id, 'Quincy Coordinator', 'quincy@advancecabs.com', '9708888888', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'ADVANCE01'
UNION ALL
SELECT v.vendor_id, 'Rachel Manager', 'rachel@transporthub.com', '9709999999', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'HUB01'
UNION ALL
SELECT v.vendor_id, 'Steve Lead', 'steve@classiccars.com', '9710000000', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', true FROM vendors v WHERE v.code = 'CLASSIC01'
ON CONFLICT (email) DO NOTHING;

-- Vehicle Types
INSERT INTO vehicle_types (vendor_id, name, description, is_active) 
SELECT v.vendor_id, 'Sedan', 'Standard sedan car', true FROM vendors v WHERE v.code = 'PREM01'
UNION ALL 
SELECT v.vendor_id, 'SUV', 'Sport utility vehicle', true FROM vendors v WHERE v.code = 'CITY01'
UNION ALL
SELECT v.vendor_id, 'Hatchback', 'Compact hatchback car', true FROM vendors v WHERE v.code = 'FLEET01'
UNION ALL
SELECT v.vendor_id, 'Minivan', 'Multi-purpose van', true FROM vendors v WHERE v.code = 'SWIFT01'
UNION ALL
SELECT v.vendor_id, 'Luxury', 'Luxury vehicles', true FROM vendors v WHERE v.code = 'SAFE01'
UNION ALL
SELECT v.vendor_id, 'Electric', 'Electric cars', true FROM vendors v WHERE v.code = 'URBAN01'
UNION ALL
SELECT v.vendor_id, 'Hybrid', 'Hybrid cars', true FROM vendors v WHERE v.code = 'METRO01'
UNION ALL
SELECT v.vendor_id, 'Truck', 'Cargo trucks', true FROM vendors v WHERE v.code = 'ELITE01'
UNION ALL
SELECT v.vendor_id, 'Bus', 'Passenger buses', true FROM vendors v WHERE v.code = 'ROYAL01'
UNION ALL
SELECT v.vendor_id, 'Motorcycle', 'Two-wheeler motorcycles', true FROM vendors v WHERE v.code = 'SPEED01'
UNION ALL
SELECT v.vendor_id, 'Convertible', 'Convertible cars', true FROM vendors v WHERE v.code = 'BUDGET01'
UNION ALL
SELECT v.vendor_id, 'Pickup', 'Pickup trucks', true FROM vendors v WHERE v.code = 'STAR01'
UNION ALL
SELECT v.vendor_id, 'Crossover', 'Crossover SUVs', true FROM vendors v WHERE v.code = 'GO01'
UNION ALL
SELECT v.vendor_id, 'Coupe', 'Coupe cars', true FROM vendors v WHERE v.code = 'QUICK01'
UNION ALL
SELECT v.vendor_id, 'Wagon', 'Station wagons', true FROM vendors v WHERE v.code = 'EASY01'
UNION ALL
SELECT v.vendor_id, 'Offroad', 'Offroad vehicles', true FROM vendors v WHERE v.code = 'COMFORT01'
UNION ALL
SELECT v.vendor_id, 'Limousine', 'Limousines', true FROM vendors v WHERE v.code = 'RELIABLE01'
UNION ALL
SELECT v.vendor_id, 'Mini Truck', 'Small trucks', true FROM vendors v WHERE v.code = 'ADVANCE01'
UNION ALL
SELECT v.vendor_id, 'Jeep', 'Jeep-style vehicles', true FROM vendors v WHERE v.code = 'HUB01'
UNION ALL
SELECT v.vendor_id, 'Van', 'Cargo and passenger vans', true FROM vendors v WHERE v.code = 'CLASSIC01'
ON CONFLICT (vendor_id, name) DO NOTHING;

-- Drivers
INSERT INTO drivers (vendor_id, name, code, email, phone, password, license_number, is_active) 
SELECT v.vendor_id, 'Ravi Kumar', 'DRV001', 'ravi.kumar@fleet.com', '9000000001', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12345', true FROM vendors v WHERE v.code = 'PREM01'
UNION ALL
SELECT v.vendor_id, 'Sunil Singh', 'DRV002', 'sunil.singh@fleet.com', '9000000002', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12346', true FROM vendors v WHERE v.code = 'CITY01'
UNION ALL
SELECT v.vendor_id, 'Amit Sharma', 'DRV003', 'amit.sharma@fleet.com', '9000000003', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12347', true FROM vendors v WHERE v.code = 'FLEET01'
UNION ALL
SELECT v.vendor_id, 'Pooja Verma', 'DRV004', 'pooja.verma@fleet.com', '9000000004', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12348', true FROM vendors v WHERE v.code = 'SWIFT01'
UNION ALL
SELECT v.vendor_id, 'Rahul Mehra', 'DRV005', 'rahul.mehra@fleet.com', '9000000005', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12349', true FROM vendors v WHERE v.code = 'SAFE01'
UNION ALL
SELECT v.vendor_id, 'Sneha Patel', 'DRV006', 'sneha.patel@fleet.com', '9000000006', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12350', true FROM vendors v WHERE v.code = 'URBAN01'
UNION ALL
SELECT v.vendor_id, 'Mohit Jain', 'DRV007', 'mohit.jain@fleet.com', '9000000007', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12351', true FROM vendors v WHERE v.code = 'METRO01'
UNION ALL
SELECT v.vendor_id, 'Vikas Gupta', 'DRV008', 'vikas.gupta@fleet.com', '9000000008', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12352', true FROM vendors v WHERE v.code = 'ELITE01'
UNION ALL
SELECT v.vendor_id, 'Neha Yadav', 'DRV009', 'neha.yadav@fleet.com', '9000000009', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12353', true FROM vendors v WHERE v.code = 'ROYAL01'
UNION ALL
SELECT v.vendor_id, 'Deepak Joshi', 'DRV010', 'deepak.joshi@fleet.com', '9000000010', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12354', true FROM vendors v WHERE v.code = 'SPEED01'
UNION ALL
SELECT v.vendor_id, 'Suman Rao', 'DRV011', 'suman.rao@fleet.com', '9000000011', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12355', true FROM vendors v WHERE v.code = 'BUDGET01'
UNION ALL
SELECT v.vendor_id, 'Arun Mishra', 'DRV012', 'arun.mishra@fleet.com', '9000000012', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12356', true FROM vendors v WHERE v.code = 'STAR01'
UNION ALL
SELECT v.vendor_id, 'Geeta Sharma', 'DRV013', 'geeta.sharma@fleet.com', '9000000013', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12357', true FROM vendors v WHERE v.code = 'GO01'
UNION ALL
SELECT v.vendor_id, 'Ramesh Kumar', 'DRV014', 'ramesh.kumar@fleet.com', '9000000014', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12358', true FROM vendors v WHERE v.code = 'QUICK01'
UNION ALL
SELECT v.vendor_id, 'Priya Singh', 'DRV015', 'priya.singh@fleet.com', '9000000015', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12359', true FROM vendors v WHERE v.code = 'EASY01'
UNION ALL
SELECT v.vendor_id, 'Manish Agarwal', 'DRV016', 'manish.agarwal@fleet.com', '9000000016', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12360', true FROM vendors v WHERE v.code = 'COMFORT01'
UNION ALL
SELECT v.vendor_id, 'Kiran Bedi', 'DRV017', 'kiran.bedi@fleet.com', '9000000017', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12361', true FROM vendors v WHERE v.code = 'RELIABLE01'
UNION ALL
SELECT v.vendor_id, 'Shweta Tiwari', 'DRV018', 'shweta.tiwari@fleet.com', '9000000018', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12362', true FROM vendors v WHERE v.code = 'ADVANCE01'
UNION ALL
SELECT v.vendor_id, 'Suresh Raina', 'DRV019', 'suresh.raina@fleet.com', '9000000019', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12363', true FROM vendors v WHERE v.code = 'HUB01'
UNION ALL
SELECT v.vendor_id, 'Divya Desai', 'DRV020', 'divya.desai@fleet.com', '9000000020', '$2a$12$1JE/73zCcRZfRWCFTLXYx.wNT1mzF.KT1qkcJ.4Hhg2lKQXfJ44EO', 'DL12364', true FROM vendors v WHERE v.code = 'CLASSIC01'
ON CONFLICT (email) DO NOTHING;

-- Vehicles
INSERT INTO vehicles (vehicle_type_id, vendor_id, driver_id, rc_number, rc_expiry_date, is_active)
SELECT vt.vehicle_type_id, vt.vendor_id, d.driver_id, 
       'RC' || LPAD((ROW_NUMBER() OVER (ORDER BY vt.vehicle_type_id))::text, 5, '0'), 
       CURRENT_DATE + INTERVAL '2 years', 
       true
FROM vehicle_types vt
JOIN drivers d ON vt.vendor_id = d.vendor_id
LIMIT 20
ON CONFLICT (rc_number) DO NOTHING;

-- Weekoff Configs for Employees
INSERT INTO weekoff_configs (employee_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday)
SELECT employee_id, 
       false, -- monday
       false, -- tuesday
       false, -- wednesday
       false, -- thursday
       false, -- friday
       true,  -- saturday
       true   -- sunday
FROM employees
ON CONFLICT (employee_id) DO NOTHING;

-- Bookings
INSERT INTO bookings (employee_id, shift_id, booking_date, status, team_id, pickup_location, drop_location)
SELECT 
    e.employee_id,
    s.shift_id,
    CURRENT_DATE + (i % 7) * INTERVAL '1 day',
    'Pending'::booking_status_enum,
    e.team_id,
    'Employee Home Address ' || e.employee_id,
    'Office Location ' || e.team_id
FROM employees e
CROSS JOIN (
    SELECT shift_id FROM shifts ORDER BY shift_id LIMIT 5
) s
CROSS JOIN generate_series(1, 4) as i
ON CONFLICT DO NOTHING;

-- Routes
INSERT INTO routes (shift_id, route_code, status, planned_distance_km, planned_duration_minutes)
SELECT 
    s.shift_id,
    'RT-' || TO_CHAR(CURRENT_DATE + (i % 7) * INTERVAL '1 day', 'YYYYMMDD') || '-' || s.shift_id,
    'Planned'::route_status_enum,
    (RANDOM() * 30 + 5)::numeric(10,2),
    (RANDOM() * 60 + 20)::integer
FROM shifts s
CROSS JOIN generate_series(1, 5) as i
WHERE s.shift_id IN (SELECT shift_id FROM shifts LIMIT 10)
ON CONFLICT (route_code) DO NOTHING;

-- Route Bookings
WITH bookings_cte AS (
    SELECT b.booking_id, b.shift_id 
    FROM bookings b 
    ORDER BY b.booking_id 
    LIMIT 50
),
routes_cte AS (
    SELECT r.route_id, r.shift_id
    FROM routes r
    ORDER BY r.route_id
)
INSERT INTO route_bookings (route_id, booking_id, planned_eta_minutes)
SELECT 
    r.route_id,
    b.booking_id,
    (RANDOM() * 45 + 5)::integer
FROM bookings_cte b
JOIN routes_cte r ON b.shift_id = r.shift_id
LIMIT 40
ON CONFLICT DO NOTHING;

-- Assign vehicles and drivers to routes
UPDATE routes r
SET 
    assigned_vendor_id = v.vendor_id,
    assigned_vehicle_id = ve.vehicle_id,
    assigned_driver_id = ve.driver_id,
    status = 'Assigned'::route_status_enum
FROM vehicles ve
JOIN vendors v ON ve.vendor_id = v.vendor_id
WHERE r.route_id % 3 = 0 
AND ve.driver_id IS NOT NULL
AND r.status = 'Planned'::route_status_enum
AND ve.vehicle_id IN (SELECT vehicle_id FROM vehicles WHERE driver_id IS NOT NULL LIMIT 10);

