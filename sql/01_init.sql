-- Initialize database schema based on new_db.sql

-- DROP SCHEMA public;

-- Create schema without specifying an owner
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

-- Create sequences
CREATE SEQUENCE IF NOT EXISTS bookings_booking_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS drivers_driver_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS employees_employee_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS shifts_shift_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS teams_team_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS tenants_tenant_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS vehicle_types_vehicle_type_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS vehicles_vehicle_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS vendor_users_vendor_user_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS vendors_vendor_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS weekoff_configs_weekoff_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS routes_route_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

CREATE SEQUENCE IF NOT EXISTS route_bookings_route_booking_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;

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
	team_id serial4 NOT NULL,
	name varchar(150) NOT NULL,
	description text NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT teams_name_key UNIQUE (name),
	CONSTRAINT teams_pkey PRIMARY KEY (team_id)
);

CREATE TABLE IF NOT EXISTS tenants (
	tenant_id serial4 NOT NULL,
	name varchar(150) NOT NULL,
	address varchar(255) NULL,
	longitude numeric(9, 6) NULL,
	latitude numeric(9, 6) NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT tenants_name_key UNIQUE (name),
	CONSTRAINT tenants_pkey PRIMARY KEY (tenant_id)
);

CREATE TABLE IF NOT EXISTS vendors (
	vendor_id serial4 NOT NULL,
	name varchar(150) NOT NULL,
	code varchar(50) NULL,
	email varchar(150) NULL,
	phone varchar(20) NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT vendors_code_key UNIQUE (code),
	CONSTRAINT vendors_email_key UNIQUE (email),
	CONSTRAINT vendors_phone_key UNIQUE (phone),
	CONSTRAINT vendors_pkey PRIMARY KEY (vendor_id)
);

CREATE TABLE IF NOT EXISTS shifts (
	shift_id serial4 NOT NULL,
	shift_code varchar(50) NOT NULL,
	log_type public."shift_log_type_enum" NOT NULL,
	shift_time time NOT NULL,
	pickup_type public."pickup_type_enum" NULL,
	gender public."gender_enum" NULL,
	waiting_time_minutes int4 DEFAULT 0 NOT NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT shifts_pkey PRIMARY KEY (shift_id),
	CONSTRAINT shifts_shift_code_key UNIQUE (shift_code)
);

CREATE TABLE IF NOT EXISTS drivers (
	driver_id serial4 NOT NULL,
	vendor_id int4 NOT NULL,
	name varchar(150) NOT NULL,
	code varchar(50) NOT NULL,
	email varchar(150) NOT NULL,
	phone varchar(20) NOT NULL,
	gender public."gender_enum" NULL,
	password varchar(255) NOT NULL,
	date_of_joining date NULL,
	date_of_birth date NULL,
	permanent_address text NULL,
	current_address text NULL,
	bg_verify_status public."verification_status_enum" NULL,
	bg_verify_date date NULL,
	bg_verify_url text NULL,
	police_verify_status public."verification_status_enum" NULL,
	police_verify_date date NULL,
	police_verify_url text NULL,
	medical_verify_status public."verification_status_enum" NULL,
	medical_verify_date date NULL,
	medical_verify_url text NULL,
	training_verify_status public."verification_status_enum" NULL,
	training_verify_date date NULL,
	training_verify_url text NULL,
	eye_verify_status public."verification_status_enum" NULL,
	eye_verify_date date NULL,
	eye_verify_url text NULL,
	license_number varchar(100) NULL,
	license_expiry_date date NULL,
	induction_status public."verification_status_enum" NULL,
	induction_date date NULL,
	induction_url text NULL,
	badge_number varchar(100) NULL,
	badge_expiry_date date NULL,
	badge_url text NULL,
	alt_govt_id_number varchar(20) NULL,
	alt_govt_id_type varchar(50) NULL,
	alt_govt_id_url text NULL,
	photo_url text NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT drivers_badge_number_key UNIQUE (badge_number),
	CONSTRAINT drivers_email_key UNIQUE (email),
	CONSTRAINT drivers_phone_key UNIQUE (phone),
	CONSTRAINT drivers_pkey PRIMARY KEY (driver_id),
	CONSTRAINT drivers_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS employees (
	employee_id serial4 NOT NULL,
	name varchar(150) NOT NULL,
	employee_code varchar(50) NULL,
	email varchar(150) NOT NULL,
	password varchar(255) NOT NULL,
	team_id int4 NULL,
	phone varchar(20) NOT NULL,
	alternate_phone varchar(20) NULL,
	special_needs text NULL,
	special_needs_start_date date NULL,
	special_needs_end_date date NULL,
	address text NULL,
	latitude numeric(9, 6) NULL,
	longitude numeric(9, 6) NULL,
	gender public."gender_enum" NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT employees_email_key UNIQUE (email),
	CONSTRAINT employees_employee_code_key UNIQUE (employee_code),
	CONSTRAINT employees_phone_key UNIQUE (phone),
	CONSTRAINT employees_pkey PRIMARY KEY (employee_id),
	CONSTRAINT employees_team_id_fkey FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS vehicle_types (
	vehicle_type_id serial4 NOT NULL,
	vendor_id int4 NOT NULL,
	name varchar(150) NOT NULL,
	description text NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT vehicle_types_pkey PRIMARY KEY (vehicle_type_id),
	CONSTRAINT vehicle_types_vendor_id_name_key UNIQUE (vendor_id, name),
	CONSTRAINT vehicle_types_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vehicles (
	vehicle_id serial4 NOT NULL,
	vehicle_type_id int4 NOT NULL,
	vendor_id int4 NOT NULL,
	driver_id int4 NULL,
	rc_number varchar(100) NOT NULL,
	rc_expiry_date date NULL,
	description text NULL,
	puc_expiry_date date NULL,
	puc_url text NULL,
	fitness_expiry_date date NULL,
	fitness_url text NULL,
	tax_receipt_date date NULL,
	tax_receipt_url text NULL,
	insurance_expiry_date date NULL,
	insurance_url text NULL,
	permit_expiry_date date NULL,
	permit_url text NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT vehicles_pkey PRIMARY KEY (vehicle_id),
	CONSTRAINT vehicles_rc_number_key UNIQUE (rc_number),
	CONSTRAINT vehicles_driver_id_fkey FOREIGN KEY (driver_id) REFERENCES drivers(driver_id) ON DELETE SET NULL,
	CONSTRAINT vehicles_vehicle_type_id_fkey FOREIGN KEY (vehicle_type_id) REFERENCES vehicle_types(vehicle_type_id) ON DELETE CASCADE,
	CONSTRAINT vehicles_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vendor_users (
	vendor_user_id serial4 NOT NULL,
	vendor_id int4 NOT NULL,
	name varchar(150) NOT NULL,
	email varchar(150) NOT NULL,
	phone varchar(20) NOT NULL,
	password varchar(255) NOT NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT vendor_users_email_key UNIQUE (email),
	CONSTRAINT vendor_users_phone_key UNIQUE (phone),
	CONSTRAINT vendor_users_pkey PRIMARY KEY (vendor_user_id),
	CONSTRAINT vendor_users_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weekoff_configs (
	weekoff_id serial4 NOT NULL,
	employee_id int4 NOT NULL,
	monday bool DEFAULT false NOT NULL,
	tuesday bool DEFAULT false NOT NULL,
	wednesday bool DEFAULT false NOT NULL,
	thursday bool DEFAULT false NOT NULL,
	friday bool DEFAULT false NOT NULL,
	saturday bool DEFAULT false NOT NULL,
	sunday bool DEFAULT false NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT weekoff_configs_employee_id_key UNIQUE (employee_id),
	CONSTRAINT weekoff_configs_pkey PRIMARY KEY (weekoff_id),
	CONSTRAINT weekoff_configs_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bookings (
	booking_id serial4 NOT NULL,
	employee_id int4 NOT NULL,
	shift_id int4 NULL,
	booking_date date NOT NULL,
	pickup_latitude float8 NULL,
	pickup_longitude float8 NULL,
	pickup_location varchar(255) NULL,
	drop_latitude float8 NULL,
	drop_longitude float8 NULL,
	drop_location varchar(255) NULL,
	status public."booking_status_enum" DEFAULT 'Pending'::booking_status_enum NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	team_id int4 NULL,
	CONSTRAINT bookings_pkey PRIMARY KEY (booking_id),
	CONSTRAINT bookings_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
	CONSTRAINT bookings_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE,
	CONSTRAINT bookings_team_id_fkey FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS routes (
	route_id serial4 NOT NULL,
	shift_id int4 NULL,
	route_code varchar(100) NOT NULL,
	status public."route_status_enum" DEFAULT 'Planned'::route_status_enum NOT NULL,
	planned_distance_km float8 NULL,
	planned_duration_minutes int4 NULL,
	actual_distance_km float8 NULL,
	actual_duration_minutes int4 NULL,
	actual_start_time timestamp NULL,
	actual_end_time timestamp NULL,
	optimized_polyline text NULL,
	assigned_vendor_id int4 NULL,
	assigned_vehicle_id int4 NULL,
	assigned_driver_id int4 NULL,
	is_active bool DEFAULT true NOT NULL,
	version int4 DEFAULT 1 NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT routes_pkey PRIMARY KEY (route_id),
	CONSTRAINT routes_route_code_key UNIQUE (route_code),
	CONSTRAINT routes_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES shifts(shift_id) ON DELETE CASCADE,
	CONSTRAINT routes_assigned_vendor_id_fkey FOREIGN KEY (assigned_vendor_id) REFERENCES vendors(vendor_id) ON DELETE SET NULL,
	CONSTRAINT routes_assigned_vehicle_id_fkey FOREIGN KEY (assigned_vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE SET NULL,
	CONSTRAINT routes_assigned_driver_id_fkey FOREIGN KEY (assigned_driver_id) REFERENCES drivers(driver_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_routes_shift_status ON routes (shift_id, status);

CREATE TABLE IF NOT EXISTS route_bookings (
	route_booking_id serial4 NOT NULL,
	route_id int4 NOT NULL,
	booking_id int4 NOT NULL,
	planned_eta_minutes int4 NULL,
	actual_arrival_time timestamp NULL,
	actual_departure_time timestamp NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT route_bookings_pkey PRIMARY KEY (route_booking_id),
	CONSTRAINT route_bookings_route_id_fkey FOREIGN KEY (route_id) REFERENCES routes(route_id) ON DELETE CASCADE,
	CONSTRAINT route_bookings_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_route_bookings_route ON route_bookings (route_id);
