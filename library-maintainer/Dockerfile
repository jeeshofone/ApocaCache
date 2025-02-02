# Build stage
FROM python:3.11-slim as builder

WORKDIR /build
COPY requirements.txt .

RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# Runtime stage
FROM python:3.11-slim

# Install curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy wheels from builder
COPY --from=builder /build/wheels /wheels
COPY --from=builder /build/requirements.txt .

# Install dependencies
RUN pip install --no-cache /wheels/*

# Copy application code
COPY src/ .

# Create necessary directories
RUN mkdir -p /data /config

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANGUAGE_FILTER="" \
    UPDATE_SCHEDULE="0 2 1 * *" \
    DOWNLOAD_ALL="false"

# Run as non-root user
RUN useradd -m -r -u 1000 kiwix && \
    chown -R kiwix:kiwix /app /data /config
USER kiwix

VOLUME ["/data", "/config"]

CMD ["python", "main.py"] 