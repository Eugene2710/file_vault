FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry with export plugin
RUN pip install poetry==1.8.5

# Copy Poetry files
COPY pyproject.toml poetry.lock ./

# Export dependencies to requirements.txt and install with pip
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p media staticfiles data

# Set permissions
RUN chmod -R 777 data media staticfiles

# Collect static files
RUN python manage.py collectstatic --noinput

# Make start script executable
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"] 