FROM python:3.11-slim

# Never buffer stdout/stderr — every log line is visible in docker logs immediately
ENV PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

# Install system dependencies including build tools for Python packages
RUN apt-get update && apt-get install -y \
    postgresql-client \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files (this will be overridden by volume mount in development)
COPY . .

# Expose port
EXPOSE 8000

# Run via python main.py so uvicorn uses log_config=None and never calls
# logging.config.dictConfig() — keeping our StreamHandler and logger state intact.
CMD ["python", "main.py"]
