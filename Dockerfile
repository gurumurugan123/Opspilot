# OpsPilot Core Backend & SRE Agent Dockerfile (Phase 9)
FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies (curl for healthchecks, build-essential for C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create non-root system user for secure container execution
RUN useradd -u 1000 -m -s /bin/bash opspilot && \
    chown -R opspilot:opspilot /app

USER opspilot

EXPOSE 8000

# Default entrypoint: Run Django API server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
