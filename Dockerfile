FROM python:3.11-slim

WORKDIR /app

# Ensure forked processes (Celery workers) can import modules from /app
ENV PYTHONPATH=/app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5002

# Default: run Flask via Gunicorn (overridden for celery/consumer containers)
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "wsgi:application"]
