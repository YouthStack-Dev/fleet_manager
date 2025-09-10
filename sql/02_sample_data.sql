-- Insert sample user data

-- Insert users
INSERT INTO users (username, email, full_name, role) VALUES
('admin', 'admin@fleetmanager.com', 'Admin User', 'administrator'),
('driver1', 'driver1@fleetmanager.com', 'John Doe', 'driver'),
('driver2', 'driver2@fleetmanager.com', 'Jane Smith', 'driver'),
('manager1', 'manager1@fleetmanager.com', 'Robert Johnson', 'manager'),
('dispatcher1', 'dispatch@fleetmanager.com', 'Emily Davis', 'dispatcher');

-- Insert vehicles
INSERT INTO vehicles (license_plate, model, year, status, assigned_to) VALUES
('ABC123', 'Toyota Camry', 2020, 'active', 2),
('XYZ789', 'Honda Civic', 2021, 'active', 3),
('DEF456', 'Ford F-150', 2019, 'maintenance', NULL),
('GHI789', 'Tesla Model 3', 2022, 'active', NULL),
('JKL012', 'Chevrolet Malibu', 2018, 'inactive', NULL);

-- Insert user permissions
INSERT INTO user_permissions (user_id, resource, permission, granted_by) VALUES
(1, 'all', 'admin', 1),
(2, 'vehicles', 'read', 1),
(3, 'vehicles', 'read', 1),
(4, 'users', 'write', 1),
(4, 'vehicles', 'write', 1),
(5, 'vehicles', 'write', 1);
