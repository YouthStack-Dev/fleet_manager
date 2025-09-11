FROM python:3.9-slim

WORKDIR /app

# Install PostgreSQL client tools for database initialization first
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY scripts/ ./scripts/
COPY sql/ ./sql/

# Create initialization script to run SQL files
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "Waiting for PostgreSQL to start..."\n\
\n\
# Wait for PostgreSQL to be ready\n\
export PGPASSWORD=$POSTGRES_PASSWORD\n\
until pg_isready -h $POSTGRES_HOST -U $POSTGRES_USER; do\n\
  echo "Waiting for PostgreSQL to become available..."\n\
  sleep 2\n\
done\n\
\n\
echo "PostgreSQL is up - executing database initialization scripts..."\n\
\n\
# Check if tables exist to prevent re-running initialization on container restart\n\
TABLES=$(psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '\''public'\'';")\n\
\n\
if [ "$TABLES" -eq "0" ] || [ "$FORCE_DB_INIT" = "true" ]; then\n\
  echo "Initializing database schema..."\n\
  psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -f /app/sql/01_init.sql\n\
  \n\
  echo "Adding sample data..."\n\
  psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -f /app/sql/02_sample_data.sql\n\
  \n\
  echo "Database initialization complete."\n\
else\n\
  echo "Database already initialized. Skipping initialization."\n\
fi\n\
\n\
echo "Starting the Flask application..."\n\
exec python /app/app.py\n\
' > /app/entrypoint.sh

# Make the initialization script executable
RUN chmod +x /app/entrypoint.sh

# Create a simple health check API
RUN echo 'from flask import Flask\nimport psycopg2\nimport os\nimport time\n\napp = Flask(__name__)\n\n@app.route("/health")\ndef health_check():\n    try:\n        conn = psycopg2.connect(\n            host=os.environ.get("POSTGRES_HOST", "localhost"),\n            database=os.environ.get("POSTGRES_DB", "fleet_db"),\n            user=os.environ.get("POSTGRES_USER", "fleetadmin"),\n            password=os.environ.get("POSTGRES_PASSWORD", "fleetpass")\n        )\n        conn.close()\n        return {"status": "healthy", "database": "connected"}, 200\n    except Exception as e:\n        return {"status": "unhealthy", "error": str(e)}, 500\n\n@app.route("/")\ndef home():\n    return {"message": "Fleet Manager API"}\n\nif __name__ == "__main__":\n    app.run(host="0.0.0.0", port=8080)\n' > app.py

# Expose port
EXPOSE 8080

# Run the initialization script as entrypoint
CMD ["/app/entrypoint.sh"]
