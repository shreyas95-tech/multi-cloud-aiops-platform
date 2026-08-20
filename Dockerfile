# Multi-Cloud AIOps Platform
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY uploads/ /app/uploads/

# Create uploads directory if it doesn't exist
RUN mkdir -p /app/uploads/kb

# Set environment variables
ENV PYTHONPATH=/app
ENV JWT_SECRET_KEY=change-this-in-production
ENV DATABASE_URL=postgresql://aiopsadmin:AiOps2024Secure!@aiops-db.ctq62w4so4tn.ap-south-1.rds.amazonaws.com:5432/aiopsplatform

# Expose ports
EXPOSE 8000

# Start the application
CMD ["python", "-m", "backend.main"]
