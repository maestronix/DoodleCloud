#!/bin/sh
set -e

echo "Waiting for database to be ready..."
max_retries=30
count=0

while [ $count -lt $max_retries ]; do
    if python -c "import database; conn = database.get_connection(); exit(0 if conn else 1)" 2>/dev/null; then
        echo "Database connection successful!"
        break
    fi
    count=$((count + 1))
    echo "Attempt $count/$max_retries: Database not ready yet, waiting..."
    sleep 2
done

if [ $count -eq $max_retries ]; then
    echo "ERROR: Could not connect to database after $max_retries attempts"
    exit 1
fi

echo "Initializing database schema..."
python -c "import database; database.init_db()"

echo "Starting application..."
exec python gui/app.py
