# Multi-stage Dockerfile for ImpleGym
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies in virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY implegym ./implegym
RUN pip install --no-cache-dir --upgrade pip hatchling && \
    pip install --no-cache-dir .

# Production Runtime Stage
FROM python:3.12-slim AS runner

WORKDIR /app

# Install runtime C++ compilers (GCC, Clang) and PostgreSQL client libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    clang \
    libpq5 \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY implegym /app/implegym
COPY README.md /app/README.md

EXPOSE 8000

ENV PORT=8000
ENV HOST=0.0.0.0

CMD ["python", "-m", "implegym.cli", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]
