-- DROP SCHEMA public;

CREATE SCHEMA public AUTHORIZATION servicemgr_user;

-- DROP TYPE public."booking_status_enum";

CREATE TYPE public."booking_status_enum" AS ENUM (
	'Pending',
	'Confirmed',
	'Ongoing',
	'Completed',
	'Canceled');

-- DROP TYPE public."gender_enum";

CREATE TYPE public."gender_enum" AS ENUM (
	'Male',
	'Female',
	'Other');

-- DROP TYPE public."pickup_type_enum";

CREATE TYPE public."pickup_type_enum" AS ENUM (
	'Pickup',
	'Nodal');

-- DROP TYPE public."shift_log_type_enum";

CREATE TYPE public."shift_log_type_enum" AS ENUM (
	'IN',
	'OUT');

-- DROP TYPE public."verification_status_enum";

CREATE TYPE public."verification_status_enum" AS ENUM (
	'Pending',
	'Approved',
	'Rejected');

-- DROP SEQUENCE bookings_booking_id_seq;

CREATE SEQUENCE bookings_booking_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE drivers_driver_id_seq;

CREATE SEQUENCE drivers_driver_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE employees_employee_id_seq;

CREATE SEQUENCE employees_employee_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE shifts_shift_id_seq;

CREATE SEQUENCE shifts_shift_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE teams_team_id_seq;

CREATE SEQUENCE teams_team_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE tenants_tenant_id_seq;

CREATE SEQUENCE tenants_tenant_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE vehicle_types_vehicle_type_id_seq;

CREATE SEQUENCE vehicle_types_vehicle_type_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE vehicles_vehicle_id_seq;

CREATE SEQUENCE vehicles_vehicle_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE vendor_users_vendor_user_id_seq;

CREATE SEQUENCE vendor_users_vendor_user_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE vendors_vendor_id_seq;

CREATE SEQUENCE vendors_vendor_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE weekoff_configs_weekoff_id_seq;

CREATE SEQUENCE weekoff_configs_weekoff_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;-- public.shifts definition

-- Drop table

-- DROP TABLE shifts;

CREATE TABLE shifts (
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

CREATE TABLE admins ( 
    admin_id SERIAL PRIMARY KEY, 
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE,
    password VARCHAR(255) NOT NULL,  -- store a bcrypt/argon2 hash, never plaintext
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- public.teams definition

-- Drop table

-- DROP TABLE teams;

CREATE TABLE teams (
	team_id serial4 NOT NULL,
	"name" varchar(150) NOT NULL,
	description text NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT teams_name_key UNIQUE (name),
	CONSTRAINT teams_pkey PRIMARY KEY (team_id)
);


-- public.tenants definition

-- Drop table

-- DROP TABLE tenants;

CREATE TABLE tenants (
	tenant_id serial4 NOT NULL,
	"name" varchar(150) NOT NULL,
	address varchar(255) NULL,
	longitude numeric(9, 6) NULL,
	latitude numeric(9, 6) NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT tenants_name_key UNIQUE (name),
	CONSTRAINT tenants_pkey PRIMARY KEY (tenant_id)
);


-- public.vendors definition

-- Drop table

-- DROP TABLE vendors;

CREATE TABLE vendors (
	vendor_id serial4 NOT NULL,
	"name" varchar(150) NOT NULL,
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


-- public.drivers definition

-- Drop table

-- DROP TABLE drivers;

CREATE TABLE drivers (
	driver_id serial4 NOT NULL,
	vendor_id int4 NOT NULL,
	"name" varchar(150) NOT NULL,
	code varchar(50) NOT NULL,
	email varchar(150) NOT NULL,
	phone varchar(20) NOT NULL,
	gender public."gender_enum" NULL,
	"password" varchar(255) NOT NULL,
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


-- public.employees definition

-- Drop table

-- DROP TABLE employees;

CREATE TABLE employees (
	employee_id serial4 NOT NULL,
	"name" varchar(150) NOT NULL,
	employee_code varchar(50) NULL,
	email varchar(150) NOT NULL,
	"password" varchar(255) NOT NULL,
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


-- public.vehicle_types definition

-- Drop table

-- DROP TABLE vehicle_types;

CREATE TABLE vehicle_types (
	vehicle_type_id serial4 NOT NULL,
	vendor_id int4 NOT NULL,
	"name" varchar(150) NOT NULL,
	description text NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT vehicle_types_pkey PRIMARY KEY (vehicle_type_id),
	CONSTRAINT vehicle_types_vendor_id_name_key UNIQUE (vendor_id, name),
	CONSTRAINT vehicle_types_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);


-- public.vehicles definition

-- Drop table

-- DROP TABLE vehicles;

CREATE TABLE vehicles (
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


-- public.vendor_users definition

-- Drop table

-- DROP TABLE vendor_users;

CREATE TABLE vendor_users (
	vendor_user_id serial4 NOT NULL,
	vendor_id int4 NOT NULL,
	"name" varchar(150) NOT NULL,
	email varchar(150) NOT NULL,
	phone varchar(20) NOT NULL,
	"password" varchar(255) NOT NULL,
	is_active bool DEFAULT true NOT NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT vendor_users_email_key UNIQUE (email),
	CONSTRAINT vendor_users_phone_key UNIQUE (phone),
	CONSTRAINT vendor_users_pkey PRIMARY KEY (vendor_user_id),
	CONSTRAINT vendor_users_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE CASCADE
);


-- public.weekoff_configs definition

-- Drop table

-- DROP TABLE weekoff_configs;

CREATE TABLE weekoff_configs (
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


-- public.bookings definition

-- Drop table

-- DROP TABLE bookings;

CREATE TABLE bookings (
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



from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Enum, Float, Numeric, Time,
    Text, ForeignKey, UniqueConstraint, func
)
from sqlalchemy.orm import relationship
from app.database.database import Base
import enum


# ---------- ENUMS ----------
class GenderEnum(enum.Enum):
    male = "Male"
    female = "Female"
    other = "Other"


class BookingStatusEnum(enum.Enum):
    pending = "Pending"
    confirmed = "Confirmed"
    ongoing = "Ongoing"
    completed = "Completed"
    canceled = "Canceled"


class ShiftLogTypeEnum(enum.Enum):
    in_shift = "IN"
    out_shift = "OUT"


class PickupTypeEnum(enum.Enum):
    pickup = "Pickup"
    nodal = "Nodal"


class VerificationStatusEnum(enum.Enum):
    pending = "Pending"
    approved = "Approved"
    rejected = "Rejected"


# ---------- BASE MIXIN ----------
class TimestampMixin:
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


# ---------- ADMINS ----------
class Admin(Base, TimestampMixin):
    __tablename__ = "admins"

    admin_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(20), unique=True)
    password = Column(String(255), nullable=False)  # store hashed password
    is_active = Column(Boolean, default=True, nullable=False)


# ---------- SHIFTS ----------
class Shift(Base, TimestampMixin):
    __tablename__ = "shifts"

    shift_id = Column(Integer, primary_key=True, index=True)
    shift_code = Column(String(50), unique=True, nullable=False)
    log_type = Column(Enum(ShiftLogTypeEnum, native_enum=False), nullable=False)
    shift_time = Column(Time, nullable=False)
    pickup_type = Column(Enum(PickupTypeEnum, native_enum=False))
    gender = Column(Enum(GenderEnum, native_enum=False))
    waiting_time_minutes = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    bookings = relationship("Booking", back_populates="shift", cascade="all, delete-orphan")


# ---------- TEAMS ----------
class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(Text)

    employees = relationship("Employee", back_populates="team", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="team", cascade="all, delete-orphan")


# ---------- TENANTS ----------
class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    tenant_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), unique=True, nullable=False)
    address = Column(String(255))
    longitude = Column(Numeric(9, 6))
    latitude = Column(Numeric(9, 6))
    is_active = Column(Boolean, default=True, nullable=False)


# ---------- VENDORS ----------
class Vendor(Base, TimestampMixin):
    __tablename__ = "vendors"

    vendor_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    code = Column(String(50), unique=True)
    email = Column(String(150), unique=True)
    phone = Column(String(20), unique=True)
    is_active = Column(Boolean, default=True, nullable=False)

    drivers = relationship("Driver", back_populates="vendor", cascade="all, delete-orphan")
    vehicle_types = relationship("VehicleType", back_populates="vendor", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="vendor", cascade="all, delete-orphan")
    vendor_users = relationship("VendorUser", back_populates="vendor", cascade="all, delete-orphan")


# ---------- DRIVERS ----------
class Driver(Base, TimestampMixin):
    __tablename__ = "drivers"

    driver_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    code = Column(String(50), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    gender = Column(Enum(GenderEnum, native_enum=False))
    password = Column(String(255), nullable=False)
    date_of_joining = Column(Date)
    date_of_birth = Column(Date)
    permanent_address = Column(Text)
    current_address = Column(Text)

    # Verification fields
    bg_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    bg_verify_date = Column(Date)
    bg_verify_url = Column(Text)

    police_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    police_verify_date = Column(Date)
    police_verify_url = Column(Text)

    medical_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    medical_verify_date = Column(Date)
    medical_verify_url = Column(Text)

    training_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    training_verify_date = Column(Date)
    training_verify_url = Column(Text)

    eye_verify_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    eye_verify_date = Column(Date)
    eye_verify_url = Column(Text)

    license_number = Column(String(100))
    license_expiry_date = Column(Date)

    induction_status = Column(Enum(VerificationStatusEnum, native_enum=False))
    induction_date = Column(Date)
    induction_url = Column(Text)

    badge_number = Column(String(100), unique=True)
    badge_expiry_date = Column(Date)
    badge_url = Column(Text)

    alt_govt_id_number = Column(String(20))
    alt_govt_id_type = Column(String(50))
    alt_govt_id_url = Column(Text)

    photo_url = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)

    vendor = relationship("Vendor", back_populates="drivers")
    vehicles = relationship("Vehicle", back_populates="driver", cascade="all, delete-orphan")


# ---------- EMPLOYEES ----------
class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    employee_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    employee_code = Column(String(50), unique=True)
    email = Column(String(150), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="SET NULL"))
    phone = Column(String(20), unique=True, nullable=False)
    alternate_phone = Column(String(20))
    special_needs = Column(Text)
    special_needs_start_date = Column(Date)
    special_needs_end_date = Column(Date)
    address = Column(Text)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    gender = Column(Enum(GenderEnum, native_enum=False))
    is_active = Column(Boolean, default=True, nullable=False)

    team = relationship("Team", back_populates="employees")
    bookings = relationship("Booking", back_populates="employee", cascade="all, delete-orphan")
    weekoff_config = relationship("WeekoffConfig", back_populates="employee", uselist=False)


# ---------- VEHICLE TYPES ----------
class VehicleType(Base, TimestampMixin):
    __tablename__ = "vehicle_types"
    __table_args__ = (UniqueConstraint("vendor_id", "name", name="vehicle_types_vendor_id_name_key"),)

    vehicle_type_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)

    vendor = relationship("Vendor", back_populates="vehicle_types")
    vehicles = relationship("Vehicle", back_populates="vehicle_type", cascade="all, delete-orphan")


# ---------- VEHICLES ----------
class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"

    vehicle_id = Column(Integer, primary_key=True, index=True)
    vehicle_type_id = Column(Integer, ForeignKey("vehicle_types.vehicle_type_id", ondelete="CASCADE"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.driver_id", ondelete="SET NULL"))

    rc_number = Column(String(100), unique=True, nullable=False)
    rc_expiry_date = Column(Date)
    description = Column(Text)

    puc_expiry_date = Column(Date)
    puc_url = Column(Text)
    fitness_expiry_date = Column(Date)
    fitness_url = Column(Text)
    tax_receipt_date = Column(Date)
    tax_receipt_url = Column(Text)
    insurance_expiry_date = Column(Date)
    insurance_url = Column(Text)
    permit_expiry_date = Column(Date)
    permit_url = Column(Text)

    is_active = Column(Boolean, default=True, nullable=False)

    vehicle_type = relationship("VehicleType", back_populates="vehicles")
    vendor = relationship("Vendor", back_populates="vehicles")
    driver = relationship("Driver", back_populates="vehicles")


# ---------- VENDOR USERS ----------
class VendorUser(Base, TimestampMixin):
    __tablename__ = "vendor_users"

    vendor_user_id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    vendor = relationship("Vendor", back_populates="vendor_users")


# ---------- WEEKOFF CONFIGS ----------
class WeekoffConfig(Base, TimestampMixin):
    __tablename__ = "weekoff_configs"

    weekoff_id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.employee_id", ondelete="CASCADE"), unique=True, nullable=False)
    monday = Column(Boolean, default=False, nullable=False)
    tuesday = Column(Boolean, default=False, nullable=False)
    wednesday = Column(Boolean, default=False, nullable=False)
    thursday = Column(Boolean, default=False, nullable=False)
    friday = Column(Boolean, default=False, nullable=False)
    saturday = Column(Boolean, default=False, nullable=False)
    sunday = Column(Boolean, default=False, nullable=False)

    employee = relationship("Employee", back_populates="weekoff_config")


# ---------- BOOKINGS ----------
class Booking(Base, TimestampMixin):
    __tablename__ = "bookings"

    booking_id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False)
    shift_id = Column(Integer, ForeignKey("shifts.shift_id", ondelete="CASCADE"))
    booking_date = Column(Date, nullable=False)
    pickup_latitude = Column(Float)
    pickup_longitude = Column(Float)
    pickup_location = Column(String(255))
    drop_latitude = Column(Float)
    drop_longitude = Column(Float)
    drop_location = Column(String(255))
    status = Column(Enum(BookingStatusEnum, native_enum=False), default=BookingStatusEnum.pending)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="SET NULL"))

    employee = relationship("Employee", back_populates="bookings")
    shift = relationship("Shift", back_populates="bookings")
    team = relationship("Team", back_populates="bookings")


from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Enum, Float, Text,
    ForeignKey, Index, func
)
from sqlalchemy.orm import relationship
from app.database.database import Base
import enum


# ---------- ENUMS ----------
class RouteStatusEnum(enum.Enum):
    planned = "Planned"        # route suggestion generated
    assigned = "Assigned"      # vendor assigned
    in_progress = "InProgress" # driver started trip
    completed = "Completed"    # finished
    cancelled = "Cancelled"    # cancelled/invalid

# ---------- MIXIN ----------
class TimestampMixin:
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


# ---------- ROUTE ----------
class Route(Base, TimestampMixin):
    __tablename__ = "routes"

    route_id = Column(Integer, primary_key=True, index=True)
    shift_id = Column(Integer, ForeignKey("shifts.shift_id", ondelete="CASCADE"), nullable=True)

    route_code = Column(String(100), nullable=False, unique=True)  # human-friendly ID
    status = Column(Enum(RouteStatusEnum, native_enum=False), default=RouteStatusEnum.planned, nullable=False)


    # Planned summary
    planned_distance_km = Column(Float, nullable=True)
    planned_duration_minutes = Column(Integer, nullable=True)

    # Actual summary (filled post-run)
    actual_distance_km = Column(Float, nullable=True)
    actual_duration_minutes = Column(Integer, nullable=True)
    actual_start_time = Column(DateTime, nullable=True)
    actual_end_time = Column(DateTime, nullable=True)

    # Optimized polyline (reference path for driver)
    optimized_polyline = Column(Text, nullable=True)

    # Current assignment (denormalized for fast reads)
    assigned_vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True)
    assigned_vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"), nullable=True)
    assigned_driver_id = Column(Integer, ForeignKey("drivers.driver_id", ondelete="SET NULL"), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, default=1, nullable=False)  # for regeneration control

    # relationships
    shift = relationship("Shift")
    bookings = relationship("RouteBooking", back_populates="route", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_routes_shift_status", "shift_id", "status"),
    )


# ---------- ROUTE <-> BOOKING ----------
class RouteBooking(Base, TimestampMixin):
    __tablename__ = "route_bookings"

    route_booking_id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.route_id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.booking_id", ondelete="CASCADE"), nullable=False)

    # Optional per-booking ETA & actuals
    planned_eta_minutes = Column(Integer, nullable=True)
    actual_arrival_time = Column(DateTime, nullable=True)
    actual_departure_time = Column(DateTime, nullable=True)

    route = relationship("Route", back_populates="bookings")
    booking = relationship("Booking")

    __table_args__ = (
        Index("ix_route_bookings_route", "route_id"),
    )
