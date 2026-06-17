FROM python:3.11-slim

WORKDIR /app

# Install uv and curl_cffi OS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install uv

# Copy dependency files
COPY pyproject.toml .

# Install dependencies
RUN uv pip install --system -e .

# Copy application code
COPY app/ ./app/

# Create data directory (will be overridden by Fly.io volume mount)
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
