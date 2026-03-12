FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md LICENSE /app/
COPY src/ /app/src/
COPY suites/ /app/suites/

# Install Python dependencies
RUN pip install --no-cache-dir -e /app

# Create non-root user
RUN useradd -m -u 1000 llmdiff && chown -R llmdiff:llmdiff /app
USER llmdiff

# Set entrypoint
ENTRYPOINT ["llm-diff"]
CMD ["--help"]
