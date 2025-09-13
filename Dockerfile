FROM python:3.9-slim

WORKDIR /app

# Install PostgreSQL client tools for database initialization
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY sql/ ./sql/

# Expose port
EXPOSE 8000

RUN cd /app

# Run the FastAPI application with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
