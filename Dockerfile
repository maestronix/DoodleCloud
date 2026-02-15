FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p upload download auth_cache

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Expose Flask port
EXPOSE 5000

# Use entrypoint script for database initialization
ENTRYPOINT ["./entrypoint.sh"]
