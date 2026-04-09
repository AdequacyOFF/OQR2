FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Improve network resilience for dependency downloads.
ENV PIP_DEFAULT_TIMEOUT=180 \
    POETRY_REQUESTS_TIMEOUT=180

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    libreoffice-writer \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.8.3

# Copy poetry files
COPY backend/pyproject.toml backend/poetry.lock* /app/

# Configure poetry to not create virtual env
RUN poetry config virtualenvs.create false

# Install dependencies with retries to survive transient network timeouts.
RUN set -eux; \
    for i in 1 2 3 4 5; do \
        poetry install --no-root --no-interaction --no-ansi && exit 0; \
        echo "poetry install failed (attempt ${i}/5), retrying in 10s..."; \
        sleep 10; \
    done; \
    echo "poetry install failed after 5 attempts"; \
    exit 1

# Copy application code
COPY backend/src /app/src
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/

# Set PYTHONPATH
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8000

# Run migrations and start server
CMD alembic upgrade head && uvicorn olimpqr.main:app --host 0.0.0.0 --port 8000
