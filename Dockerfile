FROM python:3.9-slim

# Install PostgreSQL client tools for database initialization
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files (this will be overridden by volume mount in development)
COPY . .

# Expose port
EXPOSE 8000

# Run the FastAPI application with uvicorn with hot reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
