# Fleet Manager

A fleet management system with PostgreSQL database running in Docker.

## Setup Instructions

### Prerequisites
- Docker and Docker Compose installed
- Python 3.x (for running the optional scripts)

### Getting Started

1. Start the PostgreSQL container:
   ```bash
   docker-compose up -d
   ```

2. Connect to the database:
   ```bash
   docker exec -it fleet_postgres psql -U fleetadmin -d fleet_db
   ```

3. Run the Python script to interact with the database (optional):
   ```bash
   pip install psycopg2-binary
   python scripts/query_users.py
   ```

### Project Structure
- `docker-compose.yml` - Docker setup for PostgreSQL
- `sql/` - SQL initialization scripts
  - `01_init.sql` - Database schema setup
  - `02_sample_data.sql` - Sample user data
- `scripts/` - Utility scripts
  - `query_users.py` - Python script to query users

### Environment Variables
The PostgreSQL container uses the following environment variables:
- POSTGRES_USER: fleetadmin
- POSTGRES_PASSWORD: fleetpass
- POSTGRES_DB: fleet_db

These can be modified in the docker-compose.yml file.