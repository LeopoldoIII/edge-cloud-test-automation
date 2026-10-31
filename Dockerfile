FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first for efficient Docker layer caching
COPY requirements.txt pyproject.toml .flake8 /app/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code, feature files, tests, and configuration
COPY src/ /app/src/
COPY features/ /app/features/
COPY tests/ /app/tests/

# Install local package in editable mode
RUN pip install --no-cache-dir -e .

# Run linter, type checks, and full automated test suite with coverage enforcement
CMD ["pytest", "--cov=src", "--cov-report=term-missing", "--cov-fail-under=90", "tests/"]

