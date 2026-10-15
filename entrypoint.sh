#!/bin/bash
set -e

PORT=${PORT:-5000}
export FLASK_APP=${FLASK_APP:-app:create_app}

echo "Running database migrations..."

if [ ! -d "migrations" ]; then
    echo "Initializing database migrations..."
    flask db init || echo "Migration init failed or already exists"
fi

if [ ! -d "migrations/versions" ] || [ -z "$(ls -A migrations/versions/*.py 2>/dev/null)" ]; then
    echo "Creating initial migration..."
    flask db migrate -m "Initial migration" || echo "Migration creation failed or already exists"
fi

echo "Applying database migrations..."
flask db upgrade || echo "Migration upgrade failed or already up to date"

echo "Starting Gunicorn on port $PORT..."
exec gunicorn -w 4 -b 0.0.0.0:$PORT --timeout 120 --access-logfile - --error-logfile - run:app
